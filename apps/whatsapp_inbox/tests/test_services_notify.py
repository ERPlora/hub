"""«Tell a customer something» (FLOW-F31, WHATSAPP_INBOX-F23, F26): ``whatsapp_inbox.message.notify``, the narrow
send an automation may be granted. Only to the live conversation of exactly that international number (never a
new one, never a look-alike), free text within the customer's 24 hours and an approved template outside them, the
month's cap and the connected number respected, and the same way out as the inbox's own sending (door 5 of
erplora.com, after the COMMIT). Against the real Customers app; erplora.com is ``respx``.
"""

import datetime as dt
import json
import uuid

import httpx
import pydantic
import pytest
import respx
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import B, NOW, A, connect, ctx_for, receive, run, template

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
SEND = f"{SAAS}/internal/whatsapp/send"
NOTIFY = "whatsapp_inbox.message.notify"
ANA = "+34600111222"


def automation(scope=A, language: str = "en") -> OperationContext:
    """What a step of an automation runs with: its run as the actor, the permission of this one action and the
    app's reads (``apps.flow``'s ``_step_context``)."""
    return OperationContext(
        scope=scope,
        actor=f"flow_run:{uuid.uuid7()}",
        permissions=frozenset({get(NOTIFY).permission, "whatsapp_inbox.view"}),
        language=language,
    )


def ready(minutes_ago: int = 10, **channel) -> Conversation:
    """A connected number (with its approved templates) and Ana's conversation, her last message ``minutes_ago``."""
    connect(templates=[template("recordatorio"), template("promo", category="MARKETING", variables=0, body="¡Oferta!")], **channel)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=minutes_ago)).isoformat())
    return Conversation.objects.get(phone=ANA)


def notify(payload: dict, ctx: OperationContext | None = None):
    return run(NOTIFY, payload, ctx or automation())


def answering():
    return respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))


@pytest.fixture
def delivered(django_capture_on_commit_callbacks):
    def run_and_deliver(write):
        with django_capture_on_commit_callbacks(execute=True):
            return write()

    return run_and_deliver


TEXT = "Confirmed! We are expecting you on Friday at 10:00."
TEMPLATE = {"name": "recordatorio", "variables": ["Ana", "viernes"]}


@respx.mock
def test_within_the_24_hours_the_notice_goes_as_text_to_the_exact_number_through_erplora(delivered):
    ready()
    route = answering()

    out = delivered(lambda: notify({"phone": ANA, "text": TEXT, "template": TEMPLATE}))

    sent = json.loads(route.calls.last.request.content)
    assert (sent["hub"], sent["to"], sent["type"], sent["text"]) == ("a", ANA, "text", TEXT)
    message = Message.objects.get(pk=out.id)
    assert (message.kind, message.body, message.status, message.wa_message_id) == ("text", TEXT, "sent", "wamid.OUT")
    assert message.sent_by is None and message.host == "a"
    assert [event.payload["id"] for event in OutboxEvent.objects.filter(name="whatsapp_inbox.message.sent")] == [str(out.id)]


@respx.mock
def test_after_the_24_hours_it_goes_with_the_approved_template(delivered):
    ready(minutes_ago=3 * 24 * 60)
    route = answering()

    out = delivered(lambda: notify({"phone": ANA, "text": TEXT, "template": TEMPLATE}))

    assert json.loads(route.calls.last.request.content)["template"] == {
        "name": "recordatorio",
        "language": "es",
        "variables": ["Ana", "viernes"],
    }
    assert (out.kind, out.body) == ("template", "Hola Ana, te esperamos el viernes.")


def test_after_the_24_hours_without_a_template_nothing_leaves():
    ready(minutes_ago=3 * 24 * 60)
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "text": TEXT})
    assert refused.value.code == "whatsapp_inbox.window_closed"
    assert not Message.objects.filter(direction="outbound").exists()


def test_it_says_something_or_nothing_is_sent():
    ready()
    with pytest.raises(pydantic.ValidationError):
        notify({"phone": ANA})


@pytest.mark.parametrize("typed", ["600111222", "+34 600 111 222", "34600111222", "0034600111222", ""])
def test_only_the_exact_international_number_is_written_to(typed):
    ready()
    with pytest.raises(InvalidPayload) as refused:
        notify({"phone": typed, "text": TEXT})
    assert set(refused.value.fields) == {"phone"}
    assert not Message.objects.filter(direction="outbound").exists()


def test_a_number_without_a_conversation_gets_nothing_and_none_is_opened():
    ready()
    with pytest.raises(Conflict) as refused:
        notify({"phone": "+34600111223", "text": TEXT, "template": TEMPLATE})
    assert refused.value.code == "whatsapp_inbox.no_conversation"
    assert list(Conversation.objects.values_list("phone", flat=True)) == [ANA]
    assert not Message.objects.filter(direction="outbound").exists()


def test_an_erased_conversation_is_no_conversation():
    conversation = ready()
    conversation.erased_at = NOW
    conversation.save(update_fields=["erased_at"])
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "text": TEXT})
    assert refused.value.code == "whatsapp_inbox.no_conversation"


def test_the_month_spent_sends_nothing():
    ready(monthly_limit=150, monthly_usage=150)
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "text": TEXT})
    assert refused.value.code == "whatsapp_inbox.cap_reached"
    assert not Message.objects.filter(direction="outbound").exists()


def test_a_number_not_connected_sends_nothing():
    ready(status="not_connected")
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "text": TEXT})
    assert refused.value.code == "whatsapp_inbox.channel_not_connected"


def test_another_business_goes_by_its_own_number():
    ready()  # a's number is connected; b never connected one
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "text": TEXT}, automation(B))
    assert refused.value.code == "whatsapp_inbox.channel_not_connected"
    assert not Message.objects.filter(direction="outbound").exists()


@respx.mock
def test_the_same_key_never_sends_twice(delivered):
    ready()
    route = answering()
    key = str(uuid.uuid7())
    first = delivered(lambda: notify({"phone": ANA, "text": TEXT, "client_message_id": key}))
    again = delivered(lambda: notify({"phone": ANA, "text": TEXT, "client_message_id": key}))
    assert first.id == again.id
    assert Message.objects.filter(direction="outbound").count() == 1
    assert route.call_count == 1


def test_a_marketing_template_needs_the_customer_s_consent():
    ready(minutes_ago=3 * 24 * 60)
    with pytest.raises(Conflict) as refused:
        notify({"phone": ANA, "template": {"name": "promo"}})
    assert refused.value.code == "whatsapp_inbox.marketing_consent_missing"


def test_a_template_in_several_languages_goes_in_the_automation_s_language():
    connect(templates=[template("recordatorio"), template("recordatorio", language="en", body="Hi {{1}}, see you {{2}}.")])
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(days=3)).isoformat())
    out = notify({"phone": ANA, "template": TEMPLATE}, automation(language="en"))
    assert (Message.objects.get(pk=out.id).template_language, out.body) == ("en", "Hi Ana, see you viernes.")
    out = notify({"phone": ANA, "template": TEMPLATE}, automation(language="es"))
    assert (Message.objects.get(pk=out.id).template_language, out.body) == ("es", "Hola Ana, te esperamos el viernes.")


def test_whoever_may_reply_may_notify_and_nobody_else():
    ready()
    out = notify({"phone": ANA, "text": TEXT}, ctx_for("hub_employee"))
    assert out.kind == "text"
    reader = OperationContext(scope=A, actor="tester", permissions=frozenset({"whatsapp_inbox.view"}), language="en")
    with pytest.raises(PermissionDenied):
        notify({"phone": ANA, "text": TEXT}, reader)


def test_an_automation_may_be_granted_it_it_needs_no_person_in_front():
    op = get(NOTIFY)
    assert (op.kind, op.ai["risk"]) == ("command", "normal")
    assert op.permission == "whatsapp_inbox.reply"
