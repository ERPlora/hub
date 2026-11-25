"""Replying from the inbox and sending a template (WHATSAPP_INBOX-F32, F33): the message is kept first and handed to
erplora.com after the COMMIT, against the real Customers app; ``respx`` is the transport to erplora.com only.
"""

import datetime as dt
import json
import uuid

import httpx
import pydantic
import pytest
import respx
from django.utils import translation
from live.errors import Conflict, InvalidPayload, NotFound

from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import (
    HUB_DB,
    NOW,
    SEND,
    A,
    answering,
    card,
    connect,
    conv,
    ctx_for,
    events,
    key,
    ready,
    receive,
    run,
    send,
    stored,
    system,
    template,
)
from base.tenancy.context import current_alias

pytestmark = HUB_DB


# ── WHATSAPP_INBOX-F32 Reply from the inbox: kept first, handed to erplora.com after the COMMIT ──


@respx.mock
def test_a_text_is_kept_queued_and_leaves_only_after_the_commit(make_user, django_capture_on_commit_callbacks):
    c = ready()
    luis = make_user("luis", first_name="Luis", last_name="Gil")
    route = answering()
    k = key()
    with django_capture_on_commit_callbacks(execute=True, using=current_alias()):
        out = send({"id": str(c.id), "text": "Sí, mañana a las 10", "client_message_id": k}, ctx_for("hub_employee", actor=luis))
        # Inside the operation's transaction nothing has been asked to erplora.com.
        assert route.call_count == 0
        assert (out.status, out.wa_message_id, out.sent_by_name) == ("queued", None, "Luis Gil")
    request = route.calls.last.request
    assert json.loads(request.content) == {"hub": A.key, "to": "+34600111222", "type": "text", "text": "Sí, mañana a las 10"}
    assert request.headers["Idempotency-Key"] == k
    message = stored(out)
    assert (message.direction, message.origin, message.status, message.wa_message_id, message.sent_by) == (
        "outbound",
        "hub",
        "sent",
        "wamid.OUT",
        luis.person,
    )
    c.refresh_from_db()
    assert (c.unread_count, c.last_message_direction, c.last_message_at) == (0, "outbound", NOW)
    assert events("whatsapp_inbox.message.sent") == [{"id": str(message.id), "conversation_id": str(c.id)}]
    assert events("whatsapp_inbox.message.status_changed") == [
        {"id": str(message.id), "conversation_id": str(c.id), "status": "sent"}
    ]


@respx.mock
def test_the_same_key_twice_is_one_message_and_leaves_once(delivered):
    c = ready()
    route = answering()
    k = key()
    first = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    second = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    assert first.id == second.id
    assert route.call_count == 1
    assert Message.objects.filter(direction="outbound").count() == 1


def test_the_key_is_required_so_a_retry_of_the_assistant_never_sends_twice():
    c = ready()
    with pytest.raises(pydantic.ValidationError):
        run("whatsapp_inbox.message.send", {"id": str(c.id), "text": "Hola"})


@respx.mock
def test_after_24_hours_text_is_refused_and_nothing_is_kept():
    c = ready(sent_at=(NOW - dt.timedelta(hours=24, seconds=1)).isoformat())
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.window_closed"
    assert route.call_count == 0
    assert not Message.objects.filter(direction="outbound").exists()


@respx.mock
def test_without_a_connected_number_nothing_is_kept():
    receive("wamid.IN")
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(conv().id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.channel_not_connected"
    # The number is connected from the inbox's Settings (WHATSAPP_INBOX-F01), not in erplora.com.
    assert "in Settings" in excinfo.value.message and "erplora.com" not in excinfo.value.message
    connect(version=1, status="reconnect_needed")
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(conv().id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.channel_not_connected"
    assert route.call_count == 0
    assert not Message.objects.filter(direction="outbound").exists()


def test_without_the_saas_url_nothing_is_kept(settings):
    c = ready()
    settings.SAAS_INTERNAL_URL = ""
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.saas_unconfigured"
    assert not Message.objects.filter(direction="outbound").exists()


@respx.mock
def test_with_the_month_s_messages_spent_nothing_is_kept():
    c = ready()
    connect(version=5, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    route = answering()
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.cap_reached"
    assert route.call_count == 0


def test_with_the_month_s_messages_spent_what_customers_write_still_arrives():
    """The cap only limits what the business sends."""
    c = ready()
    connect(version=5, monthly_limit=150, monthly_usage=150, usage_month="2026-10")
    out = receive("wamid.AFTER", text="¿Tenéis hora el viernes?")
    assert out.created is True and out.conversation_id == c.id
    c.refresh_from_db()
    assert (c.unread_count, c.last_message_preview) == (2, "¿Tenéis hora el viernes?")


@respx.mock
def test_erplora_s_refusal_leaves_the_message_not_delivered_with_its_reason(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.recipient_blocked", "message": "The customer blocked the business."}})
    message = stored(delivered(lambda: send({"id": str(c.id), "text": "Hola"})))
    assert (message.status, message.error_code, message.error_message, message.wa_message_id) == (
        "failed",
        "whatsapp_inbox.send_refused",
        "The customer blocked the business.",
        None,
    )


@respx.mock
def test_erplora_s_cap_refusal_is_the_hub_s_own_cap_reached(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.cap_reached", "message": "Monthly allowance spent."}})
    message = stored(delivered(lambda: send({"id": str(c.id), "text": "Hola"})))
    assert (message.status, message.error_code) == ("failed", "whatsapp_inbox.cap_reached")


@pytest.mark.parametrize(
    ("again", "status", "code", "words"),
    [
        (
            httpx.ReadTimeout("slow"),
            "sending",
            "whatsapp_inbox.send_unknown",
            "erplora.com no ha confirmado el mensaje. Vuelve a intentarlo: nunca se envía dos veces.",
        ),
        (
            httpx.Response(409, json={"error": {"code": "whatsapp.reconnect_needed", "message": "Invalid OAuth"}}),
            "failed",
            "whatsapp_inbox.reconnect_needed",
            "El permiso de WhatsApp para tu número caducó: vuelve a conectarlo.",
        ),
        (
            httpx.Response(409, json={"error": {"code": "whatsapp.cap_reached", "message": "Monthly allowance spent."}}),
            "failed",
            "whatsapp_inbox.cap_reached",
            "Has usado todos los mensajes de WhatsApp de tu plan este mes: no se puede enviar nada hasta el mes que "
            "viene o hasta que mejores el plan.",
        ),
        # erplora.com has no number of the business: its own state, never Meta's reason, in the Hub's words.
        (
            httpx.Response(
                409, json={"error": {"code": "whatsapp.not_connected", "message": "The business has no WhatsApp number connected."}}
            ),
            "failed",
            "whatsapp_inbox.channel_not_connected",
            "WhatsApp no está conectado. Conecta el número del negocio en Ajustes para recibir y enviar mensajes.",
        ),
        # A refusal of Meta's the Hub has no name for keeps Meta's words as they came; without any, the Hub's.
        (
            httpx.Response(409, json={"error": {"code": "whatsapp.recipient_blocked", "message": "Blocked by user."}}),
            "failed",
            "whatsapp_inbox.send_refused",
            "Blocked by user.",
        ),
        (
            httpx.Response(409, json={"error": {"code": "whatsapp.meta_rejected", "message": ""}}),
            "failed",
            "whatsapp_inbox.send_refused",
            "erplora.com no ha enviado el mensaje.",
        ),
    ],
)
@respx.mock
def test_a_message_the_worker_handed_again_says_why_in_the_reader_s_language(
    delivered, fixed_clock, monkeypatch, again, status, code, words
):
    """Written in Spanish, its first hand-over got no answer; the worker (the system's context, in English) hands it
    again three minutes later. Whatever erplora.com answers, the thread read in Spanish says it in Spanish."""
    c = ready()
    respx.post(SEND).mock(side_effect=[httpx.ConnectError("refused"), again])
    with translation.override("es"):
        out = delivered(lambda: send({"id": str(c.id), "text": "Hola"}, ctx_for(language="es")))
    [first] = [row for row in run("whatsapp_inbox.message.list", {"id": str(c.id)}).rows if row.id == out.id]
    assert (first.status, first.error_message) == ("sending", "erplora.com did not answer: the message has not left. Try again.")
    monkeypatch.setattr(fixed_clock, "now", lambda: NOW + dt.timedelta(minutes=3))
    assert delivered(lambda: system("whatsapp_inbox.delivery.resume", {})).messages == 1
    with translation.override("es"):
        rows = run("whatsapp_inbox.message.list", {"id": str(c.id)}, ctx_for(language="es")).rows
    [shown] = [row for row in rows if row.id == out.id]
    assert (shown.status, shown.error_code, shown.error_message) == (status, code, words)


@respx.mock
def test_a_reason_kept_in_words_before_the_code_alone_is_still_said_in_the_reader_s_language(delivered):
    """A message written before only the code was kept holds the words of whoever wrote it: its code says it again."""
    c = ready()
    respx.post(SEND).mock(side_effect=[httpx.ReadTimeout("slow")])
    out = delivered(lambda: send({"id": str(c.id), "text": "Hola"}))
    Message.objects.filter(pk=out.id).update(error_message="erplora.com did not confirm the message. Try again: it is never sent twice.")
    with translation.override("es"):
        rows = run("whatsapp_inbox.message.list", {"id": str(c.id)}, ctx_for(language="es")).rows
    [shown] = [row for row in rows if row.id == out.id]
    assert (shown.error_code, shown.error_message) == (
        "whatsapp_inbox.send_unknown",
        "erplora.com no ha confirmado el mensaje. Vuelve a intentarlo: nunca se envía dos veces.",
    )


@respx.mock
def test_an_expired_permission_is_the_hub_s_reconnect_needed_in_its_own_words(delivered):
    """Meta's 190 (the business's permission expired or withdrawn) reaches the Hub as erplora.com's
    ``whatsapp.reconnect_needed``: the message says the number must be connected again, never Meta's raw words."""
    c = ready()
    raw = "Invalid OAuth access token - Cannot parse access token"
    answering(409, {"error": {"code": "whatsapp.reconnect_needed", "message": raw}})
    out = delivered(lambda: send({"id": str(c.id), "text": "Hola"}))
    message = stored(out)
    assert (message.status, message.error_code, message.wa_message_id) == ("failed", "whatsapp_inbox.reconnect_needed", None)
    # The row keeps the code only: the words are the Hub's, said when it is read.
    assert message.error_message == ""
    [shown] = [row for row in run("whatsapp_inbox.message.list", {"id": str(c.id)}).rows if row.id == out.id]
    assert shown.error_message == "WhatsApp's permission for your number expired: connect it again."
    assert raw not in shown.error_message and "ERPlora" not in shown.error_message


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (httpx.ConnectError("refused"), "whatsapp_inbox.saas_unreachable"),
        (httpx.Response(404, json={}), "whatsapp_inbox.saas_unreachable"),
        (httpx.ReadTimeout("slow"), "whatsapp_inbox.send_unknown"),
        (httpx.Response(502, json={}), "whatsapp_inbox.send_unknown"),
    ],
)
@respx.mock
def test_no_final_answer_keeps_it_sending_and_a_retry_uses_the_same_key(delivered, answer, code):
    c = ready()
    route = respx.post(SEND).mock(side_effect=[answer])
    k = key()
    out = delivered(lambda: send({"id": str(c.id), "text": "Hola", "client_message_id": k}))
    message = stored(out)
    assert (message.status, message.error_code, message.wa_message_id) == ("sending", code, None)
    # «Not sent · Retry»: the same key, so erplora.com never sends it twice.
    route.side_effect = [httpx.Response(200, json={"wa_message_id": "wamid.LATE"})]
    again = delivered(lambda: run("whatsapp_inbox.message.retry", {"id": str(message.id)}, ctx_for("hub_employee")))
    assert again.id == message.id
    assert route.calls.last.request.headers["Idempotency-Key"] == k
    message.refresh_from_db()
    assert (message.status, message.error_code, message.wa_message_id) == ("sent", "", "wamid.LATE")


@respx.mock
def test_a_refused_or_sent_message_is_not_retried(delivered):
    c = ready()
    answering(409, {"error": {"code": "whatsapp.recipient_blocked", "message": "Blocked."}})
    refused = delivered(lambda: send({"id": str(c.id), "text": "Hola"}))
    with pytest.raises(Conflict) as excinfo:
        run("whatsapp_inbox.message.retry", {"id": str(refused.id)})
    assert excinfo.value.code == "whatsapp_inbox.not_retryable"
    with pytest.raises(NotFound):
        run("whatsapp_inbox.message.retry", {"id": str(uuid.uuid7())})


@respx.mock
def test_an_early_status_is_matched_by_the_key_and_never_lost(delivered):
    c = ready()
    k = key()
    out = send({"id": str(c.id), "text": "Hola", "client_message_id": k})  # queued, not handed over yet
    early = system(
        "whatsapp_inbox.message.update_status",
        {"wa_message_id": "wamid.OUT", "client_message_id": k, "status": "delivered"},
    )
    assert early.model_dump() == {"updated": True, "status": "delivered"}
    message = stored(out)
    assert (message.status, message.wa_message_id) == ("delivered", "wamid.OUT")
    # erplora.com's 200 lands after it: the status never goes back to «Sent».
    answering()
    from apps.whatsapp_inbox import services

    services.deliveries.deliver(A, out.id)
    message.refresh_from_db()
    assert (message.status, message.wa_message_id) == ("delivered", "wamid.OUT")


def test_a_conversation_is_named_by_its_number_or_the_customer_s_name():
    card("Ana López", "600111222")
    c = ready()
    assert send({"conversation": "600 111 222", "text": "Hola"}).conversation_id == c.id
    assert send({"conversation": "ana lópez", "text": "Hola"}).conversation_id == c.id
    with pytest.raises(NotFound) as excinfo:
        send({"conversation": "Marta", "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.conversation_not_found"


# ── WHATSAPP_INBOX-F33 Send a template ──────────────────────────────────────────────────────────


@respx.mock
def test_a_template_goes_out_of_the_window_rendered_with_its_variables(delivered):
    c = ready(sent_at=(NOW - dt.timedelta(days=3)).isoformat())
    route = answering()
    out = delivered(lambda: send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]}}))
    assert json.loads(route.calls.last.request.content)["template"] == {
        "name": "recordatorio",
        "language": "es",
        "variables": ["Ana", "viernes"],
    }
    assert (out.kind, out.template_name, out.body) == ("template", "recordatorio", "Hola Ana, te esperamos el viernes.")
    assert stored(out).template_variables == ["Ana", "viernes"]


def test_a_template_must_be_approved_and_fully_filled_in():
    c = ready()
    with pytest.raises(InvalidPayload) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana"]}})
    assert set(excinfo.value.fields) == {"template"}
    with pytest.raises(NotFound) as excinfo:
        send({"id": str(c.id), "template": {"name": "no_existe"}})
    assert excinfo.value.code == "whatsapp_inbox.template_not_found"
    connect(version=9, templates=[template("recordatorio", status="PAUSED")])
    with pytest.raises(Conflict) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]}})
    assert excinfo.value.code == "whatsapp_inbox.template_not_approved"


def test_a_template_in_two_languages_needs_the_language():
    c = ready()
    connect(version=9, templates=[template("recordatorio"), template("recordatorio", language="en")])
    with pytest.raises(InvalidPayload) as excinfo:
        send({"id": str(c.id), "template": {"name": "recordatorio", "variables": ["a", "b"]}})
    assert set(excinfo.value.fields) == {"template"}
    out = send({"id": str(c.id), "template": {"name": "recordatorio", "language": "en", "variables": ["a", "b"]}})
    assert out.template_name == "recordatorio"


def test_marketing_needs_the_card_s_whatsapp_consent():
    c = ready()
    promo = {"id": str(c.id), "template": {"name": "promo"}}
    with pytest.raises(Conflict) as excinfo:
        send(promo)  # no card at all
    assert excinfo.value.code == "whatsapp_inbox.marketing_consent_missing"
    ana = card("Ana López", "600111222")
    run("whatsapp_inbox.conversation.link_customer", {"id": str(c.id), "customer_id": str(ana.id)})
    with pytest.raises(Conflict):
        send(promo)  # a card without consent
    run(
        "customer.consent.grant",
        {"customer_id": str(ana.id), "channel": "whatsapp", "notice_text": "¿Quieres recibir ofertas por WhatsApp?"},
    )
    assert send(promo).template_name == "promo"
    run("customer.consent.withdraw", {"customer_id": str(ana.id), "channel": "whatsapp"})
    with pytest.raises(Conflict):
        send(promo)


def test_a_template_to_a_number_that_never_wrote_opens_its_conversation():
    connect(templates=[template("recordatorio")])
    out = send({"to": "600 222 333", "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    c = Conversation.objects.get(phone="+34600222333")
    assert (out.conversation_id, c.status, c.unread_count, c.last_inbound_at) == (c.id, "open", 0, None)
    with pytest.raises(Conflict) as excinfo:
        send({"to": "600 444 555", "text": "Hola"})
    assert excinfo.value.code == "whatsapp_inbox.window_closed"
    assert not Conversation.objects.filter(phone="+34600444555").exists()


@pytest.mark.parametrize("typed", ["600222333", "600 222 333", "+34 600 222 333", "0034600222333"])
def test_a_number_typed_by_hand_goes_to_that_person_never_to_another_country(typed):
    """A number written on a card or by voice is national unless it says its country."""
    connect(templates=[template("recordatorio")])
    send({"to": typed, "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    assert list(Conversation.objects.values_list("phone", flat=True)) == ["+34600222333"]


def test_an_incomplete_number_is_refused_and_nothing_is_kept():
    connect(templates=[template("recordatorio")])
    with pytest.raises(InvalidPayload) as excinfo:
        send({"to": "600 22", "template": {"name": "recordatorio", "variables": ["Ana", "lunes"]}})
    assert "to" in excinfo.value.fields
    assert not Conversation.objects.exists() and not Message.objects.exists()


def test_marketing_to_a_number_without_conversation_reads_the_card_of_that_number():
    connect(templates=[template("promo", category="MARKETING", variables=0, body="¡Oferta!")])
    ana = card("Ana López", "600222333")
    run(
        "customer.consent.grant",
        {"customer_id": str(ana.id), "channel": "whatsapp", "notice_text": "¿Quieres recibir ofertas por WhatsApp?"},
    )
    out = send({"to": "+34 600 222 333", "template": {"name": "promo"}})
    assert Conversation.objects.get(pk=out.conversation_id).customer_id == ana.id
    with pytest.raises(Conflict) as excinfo:
        send({"to": "600 999 777", "template": {"name": "promo"}})  # nobody's card: no consent
    assert excinfo.value.code == "whatsapp_inbox.marketing_consent_missing"
