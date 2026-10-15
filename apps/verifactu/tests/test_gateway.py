"""The client of ERPlora's fiscal gateway in the SaaS (VERIFACTU-F10, F15, F27): the transport only.

The gateway is a contract (WORKBOOK «Contrato con el SaaS»): ``POST {VERIFACTU_GATEWAY_URL}/internal/verifactu/…``
with JSON, signed with HMAC-SHA256 like every ``/internal`` call. ``respx`` stands in for the SaaS here and only
here: what the AEAT answers is never invented (the answers the services read are the AEAT's real ones,
``fixtures/``). Without a gateway URL nothing is sent and nothing pretends to be.
"""

import hashlib
import hmac
import json

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
