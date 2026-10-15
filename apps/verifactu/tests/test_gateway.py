"""The client of ERPlora's fiscal gateway in the SaaS (VERIFACTU-F10, F15, F27): the transport only.

The gateway is a contract (WORKBOOK «Contrato con el SaaS»): ``POST {VERIFACTU_GATEWAY_URL}/internal/verifactu/…``
with JSON, signed with HMAC-SHA256 like every ``/internal`` call. ``respx`` stands in for the SaaS here and only
here: what the AEAT answers is never invented (the answers the services read are the AEAT's real ones,
``fixtures/``). Without a gateway URL nothing is sent and nothing pretends to be.
"""

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
import respx

from apps.verifactu import gateway

URL = "http://saas.internal:8001"
SECRET = "test-internal-secret"


@pytest.fixture
def configured(settings):
    settings.VERIFACTU_GATEWAY_URL = URL
    settings.INTERNAL_SHARED_SECRET = SECRET
    return settings


def submit():
    return gateway.submit(
        hub="a",
        nif="B12345674",
        environment="testing",
        route="erplora",
        envelope="<x/>",
    )


def test_without_a_url_there_is_no_gateway(settings, monkeypatch):
    settings.VERIFACTU_GATEWAY_URL = ""
    monkeypatch.delenv("VERIFACTU_GATEWAY_URL", raising=False)
    assert gateway.configured() is False
    with pytest.raises(gateway.NotConfigured):
        submit()


def test_the_url_may_come_from_the_environment(settings, monkeypatch):
    del settings.VERIFACTU_GATEWAY_URL
    monkeypatch.setenv("VERIFACTU_GATEWAY_URL", URL)
    assert gateway.configured() is True


@respx.mock
def test_a_submission_is_signed_like_every_internal_call(configured):
    route = respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            200, json={"aeat_status": 200, "aeat_body": "<answer/>"}
        )
    )
    reply = submit()
    request = route.calls.last.request
    body = request.content
    assert json.loads(body) == {
        "hub": "a",
        "nif": "B12345674",
        "environment": "testing",
        "route": "erplora",
        "envelope": "<x/>",
    }
    timestamp = request.headers["X-Erplora-Timestamp"]
    expected = hmac.new(
        SECRET.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Erplora-Signature"] == expected
    assert request.headers["Content-Type"] == "application/json"
    assert reply.kind == gateway.ANSWERED
    assert (reply.aeat_status, reply.aeat_body) == (200, "<answer/>")


@respx.mock
def test_an_aeat_fault_comes_back_with_the_aeats_status(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            200, json={"aeat_status": 500, "aeat_body": "<fault/>"}
        )
    )
    reply = submit()
    assert reply.kind == gateway.ANSWERED
    assert (reply.aeat_status, reply.aeat_body) == (500, "<fault/>")


@respx.mock
def test_a_refusal_of_the_gateway_names_itself(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            409,
            json={
                "error": {
                    "code": "verifactu_gateway.representation_required",
                    "message": "No approved grant.",
                }
            },
        )
    )
    reply = submit()
    assert reply.kind == gateway.REFUSED
    assert reply.code == "verifactu_gateway.representation_required"
    assert reply.message == "No approved grant."


@pytest.mark.parametrize("status", [401, 404, 500, 502, 503])
@respx.mock
def test_another_status_is_a_gateway_that_could_not_take_it(configured, status):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(status, text="down")
    )
    reply = submit()
    assert reply.kind == gateway.UNREACHABLE
    assert str(status) in reply.message


@respx.mock
def test_a_connection_that_never_opened_sent_nothing(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        side_effect=httpx.ConnectError("refused")
    )
    assert submit().kind == gateway.UNREACHABLE


@respx.mock
def test_a_request_that_left_and_never_came_back_may_have_reached_the_aeat(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        side_effect=httpx.ReadTimeout("slow")
    )
    assert submit().kind == gateway.UNKNOWN


@respx.mock
def test_an_answer_that_is_not_the_contract_is_unknown(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(200, text="<html/>")
    )
    assert submit().kind == gateway.UNKNOWN


@respx.mock
def test_a_query_goes_to_its_own_door(configured):
    route = respx.post(f"{URL}/internal/verifactu/query").mock(
        return_value=httpx.Response(200, json={"aeat_status": 200, "aeat_body": "<q/>"})
    )
    reply = gateway.query(
        hub="a", nif="B12345674", environment="testing", route="own", envelope="<q/>"
    )
    assert route.called
    assert reply.aeat_body == "<q/>"


@respx.mock
def test_the_probe_says_whether_it_can_present_without_presenting(configured):
    route = respx.post(f"{URL}/internal/verifactu/probe").mock(
        return_value=httpx.Response(
            200, json={"ready": False, "detail": "No approved grant."}
        )
    )
    reply = gateway.probe(
        hub="a", nif="B12345674", environment="production", route="erplora"
    )
    assert json.loads(route.calls.last.request.content) == {
        "hub": "a",
        "nif": "B12345674",
        "environment": "production",
        "route": "erplora",
    }
    assert reply.kind == gateway.ANSWERED
    assert (reply.ready, reply.message) == (False, "No approved grant.")


# The SaaS's real gateway (saas-next fiscal_gateway/, README «Contrato con el Hub»): the own certificate travels
# on every «own» call, and its answers other than 200 say what happened.

CERTIFICATE = gateway.Certificate(p12_base64="MIIK", password="secret")


@respx.mock
def test_the_own_route_hands_the_certificate_on_every_door(configured):
    doors = {
        door: respx.post(f"{URL}/internal/verifactu/{door}").mock(
            return_value=httpx.Response(
                200,
                json={"aeat_status": 200, "aeat_body": "<a/>", "ready": True, "detail": ""},
            )
        )
        for door in ("submit", "query", "probe")
    }
    common = {"hub": "a", "nif": "B12345674", "environment": "testing", "route": "own"}
    gateway.submit(**common, envelope="<x/>", certificate=CERTIFICATE)
    gateway.query(**common, envelope="<q/>", certificate=CERTIFICATE)
    gateway.probe(**common, certificate=CERTIFICATE)
    for route in doors.values():
        sent = json.loads(route.calls.last.request.content)
        assert sent["certificate"] == {"p12_base64": "MIIK", "password": "secret"}


@respx.mock
def test_without_a_certificate_the_body_does_not_name_one(configured):
    route = respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(200, json={"aeat_status": 200, "aeat_body": "<a/>"})
    )
    submit()
    assert "certificate" not in json.loads(route.calls.last.request.content)


def test_a_certificate_never_shows_its_material():
    assert "MIIK" not in repr(CERTIFICATE) and "secret" not in repr(CERTIFICATE)


def aeat_unreachable(sent: bool) -> httpx.Response:
    return httpx.Response(
        502,
        json={
            "error": {
                "code": "aeat_unreachable",
                "message": "The AEAT did not answer.",
                "sent": sent,
            }
        },
    )


@respx.mock
def test_an_aeat_that_never_answered_a_request_that_left_may_have_it(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(return_value=aeat_unreachable(True))
    reply = submit()
    assert reply.kind == gateway.UNKNOWN
    assert "The AEAT did not answer." in reply.message


@respx.mock
def test_an_aeat_that_could_not_be_reached_has_nothing(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(return_value=aeat_unreachable(False))
    reply = submit()
    assert reply.kind == gateway.UNREACHABLE
    assert "The AEAT did not answer." in reply.message


@respx.mock
def test_a_busy_gateway_is_tried_again(configured):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            503, json={"error": {"code": "gateway_busy", "message": "Busy."}}
        )
    )
    assert submit().kind == gateway.UNREACHABLE


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (409, "nif_mismatch"),
        (409, "representation_not_approved"),
        (409, "no_seal"),
        (409, "no_certificate"),
        (409, "certificate_invalid"),
        (409, "environment_not_allowed"),
        (413, "payload_too_large"),
        (422, "invalid_payload"),
    ],
)
@respx.mock
def test_what_the_gateway_will_never_present_is_a_refusal_with_its_code(
    configured, status, code
):
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            status,
            json={
                "error": {
                    "code": code,
                    "message": "Not presented.",
                    **({"fields": {"hub": "Not a UUID."}} if status == 422 else {}),
                }
            },
        )
    )
    reply = submit()
    assert (reply.kind, reply.code) == (gateway.REFUSED, code)
    assert reply.message.startswith("Not presented.")
    if status == 422:
        assert "hub" in reply.message


@respx.mock
def test_a_hub_the_saas_does_not_know_is_a_refusal_not_a_retry(configured):
    # saas#29: the gateway answers 404 ``hub_unknown`` when the body's ``hub`` names no hub of the SaaS; trying it
    # again as it is would be refused forever.
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            404,
            json={"error": {"code": "hub_unknown", "message": "No such hub."}},
        )
    )
    reply = submit()
    assert (reply.kind, reply.code) == (gateway.REFUSED, "hub_unknown")
    assert reply.message == "No such hub."


@respx.mock
def test_a_door_that_is_not_there_is_still_tried_again(configured):
    # A 404 without the contract's ``hub_unknown`` is a gateway not deployed yet or a wrong URL: it may come back.
    respx.post(f"{URL}/internal/verifactu/submit").mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "not_found", "message": "Not found."}}
        )
    )
    assert submit().kind == gateway.UNREACHABLE


def test_the_hub_waits_longer_than_the_gateway_waits_for_the_aeat():
    """The gateway connects to the AEAT in 5 s and reads for 30 s: the Hub reads for more than 40 s."""
    assert gateway.TIMEOUT.connect == 5.0
    assert gateway.TIMEOUT.read > 40.0


@pytest.fixture
def gateway_on_this_machine(configured):
    """A gateway listening on the loopback that answers the contract's 200: the real transport, no stand-in."""

    class Gateway(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.dumps({"aeat_status": 200, "aeat_body": "<ok/>"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    configured.VERIFACTU_GATEWAY_URL = f"http://127.0.0.1:{server.server_port}"
    yield server
    server.shutdown()
    server.server_close()


def test_a_proxy_of_the_process_never_carries_the_envelope(
    gateway_on_this_machine, monkeypatch
):
    # The envelope (and, on the own route, the business's certificate) goes straight to the SaaS's internal
    # address, as the signed authorisation does (representation.py): a proxy set in the environment is ignored.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)

    reply = submit()

    assert (reply.kind, reply.aeat_status, reply.aeat_body) == (
        gateway.ANSWERED,
        200,
        "<ok/>",
    )
