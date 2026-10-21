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


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 429])
@respx.mock
def test_a_4xx_other_than_409_means_nothing_left(status):
    # erplora.com read the request and did not take it: nothing reached Meta, a retry is safe. A 429 (go
    # slower) is never «the month is spent» (gh:hub#2649).
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


# ── A client that never crashes (area-hub HALLAZGO rv-102) ──────────────────────────────────────


def test_a_saas_url_the_client_cannot_use_is_unreachable_never_a_crash(settings):
    """httpx raises errors that are not HTTPError (an URL it cannot parse): the caller still gets an answer."""
    settings.SAAS_INTERNAL_URL = "http://saas:abc"  # httpx.InvalidURL: not an HTTPError
    assert send_text().kind == gateway.UNREACHABLE
    assert gateway.erase(hub="a", phone="+34600111222", wa_message_ids=[]) is False
    assert gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE).kind == gateway.UNREACHABLE
    assert gateway.delete_template(hub="a", name="recordatorio", language="es", meta_id="1").kind == gateway.UNREACHABLE


@respx.mock
def test_a_header_the_client_cannot_encode_is_unreachable_never_a_crash():
    """A ``ValueError`` (a key that is not ASCII) is not an HTTPError either: nothing left, and it says so."""
    route = respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.1"}))
    reply = send_text(idempotency_key="clé")
    assert reply.kind == gateway.UNREACHABLE and "could not be made" in reply.message
    assert not route.called


# ── The templates doors (WORKBOOK «Contrato con el SaaS», doors 8 and 9; WHATSAPP_INBOX-F29…F31) ──

TEMPLATES = f"{URL}/internal/whatsapp/templates"
TEMPLATES_DELETE = f"{URL}/internal/whatsapp/templates/delete"
TEMPLATE = {
    "name": "recordatorio",
    "language": "es",
    "category": "UTILITY",
    "header": "Tu cita",
    "body": "Hola {{1}}, te esperamos el {{2}}.",
    "body_examples": ["Ana", "viernes"],
    "footer": "Peluquería Ana",
    "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}],
    "meta_id": "",
}


@respx.mock
def test_a_template_is_posted_signed_with_its_key_and_200_is_meta_s_verdict():
    route = respx.post(TEMPLATES).mock(
        return_value=httpx.Response(200, json={"meta_id": "1234", "status": "PENDING"})
    )
    reply = gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE)
    assert reply == gateway.Reply(kind=gateway.ACCEPTED, meta_id="1234", status="PENDING")
    request = route.calls.last.request
    assert json.loads(request.content) == {"hub": "a", **TEMPLATE}
    assert request.headers["Idempotency-Key"] == KEY
    timestamp = request.headers[TIMESTAMP_HEADER]
    assert request.headers[SIGNATURE_HEADER] == sign("s3cret", timestamp, request.content)


@respx.mock
def test_a_409_on_a_template_is_a_refusal_with_meta_s_reason():
    respx.post(TEMPLATES).mock(
        return_value=httpx.Response(
            409, json={"error": {"code": "whatsapp.template_invalid", "message": "Template name already exists"}}
        )
    )
    reply = gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE)
    assert reply == gateway.Reply(
        kind=gateway.REFUSED, code="whatsapp.template_invalid", message="Template name already exists"
    )


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        (httpx.Response(200, json={"status": "PENDING"}), gateway.UNKNOWN),
        (httpx.Response(200, json={"meta_id": "1", "status": "SOMETHING"}), gateway.UNKNOWN),
        (httpx.Response(500, json={}), gateway.UNKNOWN),
        (httpx.Response(404, json={}), gateway.UNREACHABLE),
    ],
)
@respx.mock
def test_a_template_is_registered_only_with_meta_s_id_and_a_known_verdict(answer, kind):
    respx.post(TEMPLATES).mock(return_value=answer)
    assert gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE).kind == kind


@respx.mock
def test_a_template_with_no_connection_is_unreachable_and_with_no_answer_unknown():
    respx.post(TEMPLATES).mock(side_effect=httpx.ConnectError("refused"))
    assert gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE).kind == gateway.UNREACHABLE
    respx.post(TEMPLATES).mock(side_effect=httpx.ReadTimeout("slow"))
    assert gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE).kind == gateway.UNKNOWN


@respx.mock
def test_a_template_deletion_is_posted_signed_and_200_deleted_confirms_it():
    route = respx.post(TEMPLATES_DELETE).mock(return_value=httpx.Response(200, json={"deleted": True}))
    reply = gateway.delete_template(hub="a", name="recordatorio", language="es", meta_id="1234")
    assert reply.kind == gateway.ACCEPTED
    request = route.calls.last.request
    assert json.loads(request.content) == {"hub": "a", "name": "recordatorio", "language": "es", "meta_id": "1234"}
    timestamp = request.headers[TIMESTAMP_HEADER]
    assert request.headers[SIGNATURE_HEADER] == sign("s3cret", timestamp, request.content)


@respx.mock
def test_a_template_meta_no_longer_has_is_deleted_and_a_refusal_keeps_its_reason():
    gone = {"error": {"code": "whatsapp.template_not_found", "message": "Meta has no such template"}}
    respx.post(TEMPLATES_DELETE).mock(return_value=httpx.Response(404, json=gone))
    assert gateway.delete_template(hub="a", name="x", language="es", meta_id="").kind == gateway.ACCEPTED
    respx.post(TEMPLATES_DELETE).mock(
        return_value=httpx.Response(409, json={"error": {"code": "whatsapp.meta_unreachable", "message": "Meta"}})
    )
    reply = gateway.delete_template(hub="a", name="x", language="es", meta_id="")
    assert (reply.kind, reply.code) == (gateway.REFUSED, "whatsapp.meta_unreachable")
    respx.post(TEMPLATES_DELETE).mock(return_value=httpx.Response(200, json={"deleted": False}))
    assert gateway.delete_template(hub="a", name="x", language="es", meta_id="").kind == gateway.UNKNOWN


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(404, json={}), httpx.Response(404, text="<h1>Not Found</h1>"),
     httpx.Response(404, json={"error": {"code": "not_found", "message": "No route"}})],
)
@respx.mock
def test_a_404_that_is_not_erplora_saying_meta_has_no_such_template_deletes_nothing(answer):
    """gh:whatsapp_inbox#296: a door erplora.com does not serve yet (or a wrong address) also answers 404;
    reading it as «Meta no longer has it» would drop the template here while Meta keeps it alive."""
    respx.post(TEMPLATES_DELETE).mock(return_value=answer)
    reply = gateway.delete_template(hub="a", name="x", language="es", meta_id="1")
    assert reply.kind == gateway.UNREACHABLE and "404" in reply.message


def test_without_the_saas_url_no_template_leaves(settings):
    settings.SAAS_INTERNAL_URL = ""
    with pytest.raises(gateway.NotConfigured):
        gateway.submit_template(hub="a", idempotency_key=KEY, template=TEMPLATE)
    with pytest.raises(gateway.NotConfigured):
        gateway.delete_template(hub="a", name="x", language="es", meta_id="")
