"""The Hub's client of erplora.com's sending door (WORKBOOK «Contrato con el SaaS», door 4).

``respx`` stands in for the transport only: what is checked is the request the Hub writes (path,
signature, idempotency key, body) and how each answer is read. Nothing here is ever «sent» unless
erplora.com answered 200 with Meta's id.
"""

import json

import httpx
import pytest
import respx

from apps.whatsapp_inbox import gateway
from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

URL = "http://saas.internal:8000"
SEND = f"{URL}/internal/whatsapp/send"
KEY = "0199e000-0000-7000-8000-0000000000aa"


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_INTERNAL_URL = URL
    settings.INTERNAL_SHARED_SECRET = "s3cret"


def send_text(**overrides):
    args = {"hub": "a", "to": "+34600111222", "text": "Hola", "idempotency_key": KEY}
    args.update(overrides)
    return gateway.send(**args)


@respx.mock
def test_a_text_is_posted_signed_with_its_idempotency_key_and_200_is_sent():
    route = respx.post(SEND).mock(
        return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT1"})
    )
    reply = send_text()
    assert reply == gateway.Reply(kind=gateway.SENT, wa_message_id="wamid.OUT1")
    request = route.calls.last.request
    body = request.content
    assert json.loads(body) == {
        "hub": "a",
        "to": "+34600111222",
        "type": "text",
        "text": "Hola",
    }
    assert request.headers["Idempotency-Key"] == KEY
    assert request.headers["Content-Type"] == "application/json"
    timestamp = request.headers[TIMESTAMP_HEADER]
    assert request.headers[SIGNATURE_HEADER] == sign("s3cret", timestamp, body)


@respx.mock
def test_a_template_travels_with_its_name_language_and_variables():
    route = respx.post(SEND).mock(
        return_value=httpx.Response(200, json={"wa_message_id": "wamid.T"})
    )
    reply = gateway.send(
        hub="a",
        to="+34600111222",
        template={
            "name": "recordatorio",
            "language": "es",
            "variables": ["Ana", "viernes"],
        },
        idempotency_key=KEY,
    )
    assert reply.kind == gateway.SENT
    assert json.loads(route.calls.last.request.content) == {
        "hub": "a",
        "to": "+34600111222",
        "type": "template",
        "template": {
            "name": "recordatorio",
            "language": "es",
            "variables": ["Ana", "viernes"],
        },
    }


@respx.mock
def test_a_409_is_a_refusal_with_erplora_s_code_and_reason():
    respx.post(SEND).mock(
        return_value=httpx.Response(
            409,
            json={
                "error": {
                    "code": "whatsapp.cap_reached",
                    "message": "Monthly allowance spent.",
                }
            },
        )
    )
    assert send_text() == gateway.Reply(
        kind=gateway.REFUSED,
        code="whatsapp.cap_reached",
        message="Monthly allowance spent.",
    )


@respx.mock
def test_a_409_without_the_envelope_is_still_a_refusal():
    respx.post(SEND).mock(return_value=httpx.Response(409, text="nope"))
    reply = send_text()
    assert (reply.kind, reply.code) == (gateway.REFUSED, "whatsapp.refused")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
@respx.mock
def test_a_4xx_other_than_409_means_nothing_left(status):
    # erplora.com read the request and did not take it: nothing reached Meta, a retry is safe.
    respx.post(SEND).mock(return_value=httpx.Response(status, json={}))
    reply = send_text()
    assert reply.kind == gateway.UNREACHABLE
    assert str(status) in reply.message


@pytest.mark.parametrize("status", [500, 502, 503, 504])
@respx.mock
def test_a_5xx_may_have_reached_meta_so_it_is_unknown(status):
    # erplora.com may have called Meta before failing: «not sent» would invite a second message.
    respx.post(SEND).mock(return_value=httpx.Response(status, json={}))
    reply = send_text()
    assert reply.kind == gateway.UNKNOWN
    assert str(status) in reply.message


@respx.mock
def test_no_connection_means_nothing_left():
    respx.post(SEND).mock(side_effect=httpx.ConnectError("refused"))
    assert send_text().kind == gateway.UNREACHABLE


@respx.mock
def test_no_answer_after_sending_is_unknown():
    respx.post(SEND).mock(side_effect=httpx.ReadTimeout("slow"))
    assert send_text().kind == gateway.UNKNOWN


@respx.mock
def test_a_200_without_meta_s_id_is_unknown_never_sent():
    respx.post(SEND).mock(return_value=httpx.Response(200, json={"ok": True}))
    assert send_text().kind == gateway.UNKNOWN
    respx.post(SEND).mock(return_value=httpx.Response(200, text="<html>"))
    assert send_text().kind == gateway.UNKNOWN


def test_without_the_saas_url_nothing_is_sent(settings):
    settings.SAAS_INTERNAL_URL = ""
    assert gateway.configured() is False
    with pytest.raises(gateway.NotConfigured):
        send_text()


def test_the_timeouts_are_short():
    assert gateway.TIMEOUT.connect == 5.0
    assert gateway.TIMEOUT.read == 15.0


# ── The erasure door (WORKBOOK «Contrato con el SaaS», door 6) ──────────────────────────────────

ERASE = f"{URL}/internal/whatsapp/erase"


@respx.mock
def test_an_erasure_is_posted_signed_and_200_erased_confirms_it():
    route = respx.post(ERASE).mock(return_value=httpx.Response(200, json={"erased": True}))
    assert gateway.erase(hub="a", phone="+34600111222", wa_message_ids=["wamid.1", "wamid.2"]) is True
    request = route.calls.last.request
    assert json.loads(request.content) == {"hub": "a", "phone": "+34600111222", "wa_message_ids": ["wamid.1", "wamid.2"]}
    timestamp = request.headers[TIMESTAMP_HEADER]
    assert request.headers[SIGNATURE_HEADER] == sign("s3cret", timestamp, request.content)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, json={"erased": False}),
        httpx.Response(200, text="ok"),
        httpx.Response(404, json={}),
        httpx.Response(500, json={}),
    ],
)
@respx.mock
def test_anything_but_erased_true_is_not_a_confirmation(answer):
    respx.post(ERASE).mock(return_value=answer)
    assert gateway.erase(hub="a", phone="+34600111222", wa_message_ids=[]) is False


@respx.mock
def test_an_unreachable_saas_does_not_confirm_an_erasure():
    respx.post(ERASE).mock(side_effect=httpx.ConnectError("refused"))
    assert gateway.erase(hub="a", phone="+34600111222", wa_message_ids=[]) is False


def test_without_the_saas_url_no_erasure_is_asked(settings):
    settings.SAAS_INTERNAL_URL = ""
    with pytest.raises(gateway.NotConfigured):
        gateway.erase(hub="a", phone="+34600111222", wa_message_ids=[])
