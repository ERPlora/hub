"""What the customer taps answers a question the Hub asked (WHATSAPP_INBOX-F38, old HUB-F265).

A template's quick reply (or an interactive button or list row) comes back as a message with the option
tapped (its id and its text) and the WhatsApp id of the message it answers. The Hub keeps the option and, in
the ``whatsapp_inbox.message.received`` event, says which of its own messages asked: an app that waits for
that answer (an appointment reminder) tells two open «Yes» apart. Never absent, empty when it answers
nothing this Hub sent. Cases of the old Hub's tests: lifted by erplora.com or read from Meta's object, a
reply to another hub's message or to an unknown one leaves both empty.
"""

import datetime as dt
import uuid

import httpx
import pytest
import respx
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import NOW, connect, receive, run, template

pytestmark = pytest.mark.django_db

SEND = "http://saas.test/internal/whatsapp/send"


def asked(django_capture_on_commit_callbacks, wamid: str, **template_fields) -> Message:
    """The Hub sends a reminder template (with its quick replies) and Meta gives it ``wamid``."""
    respx.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": wamid}))
    with django_capture_on_commit_callbacks(execute=True):
        out = run(
            "whatsapp_inbox.message.send",
            {
                "conversation": "+34600111222",
                "template": {"name": "recordatorio", "variables": ["Ana", "viernes"]},
                "client_message_id": str(uuid.uuid7()),
            },
        )
    return Message.objects.get(pk=out.id)


def received_event(message_id) -> dict:
    return next(
        event.payload
        for event in OutboxEvent.objects.filter(name="whatsapp_inbox.message.received").order_by("-id")
        if event.payload["id"] == str(message_id)
    )


@pytest.fixture
def chat():
    connect(templates=[template("recordatorio", buttons=[{"type": "QUICK_REPLY", "text": "Sí"}, {"type": "QUICK_REPLY", "text": "No"}])])
    receive("wamid.HELLO", sent_at=(NOW - dt.timedelta(minutes=30)).isoformat())


@respx.mock
def test_a_tapped_option_says_which_message_of_the_hub_it_answers(chat, django_capture_on_commit_callbacks):
    first = asked(django_capture_on_commit_callbacks, "wamid.Q1")
    second = asked(django_capture_on_commit_callbacks, "wamid.Q2")
    out = receive("wamid.A2", type="button", text="Sí", reply_to="wamid.Q2", reply={"id": "Sí", "title": "Sí"})
    answer = Message.objects.get(pk=out.id)
    assert (answer.kind, answer.body, answer.reply_to, answer.reply_id) == ("button", "Sí", "wamid.Q2", "Sí")
    event = received_event(out.id)
    assert event["reply_to_message_id"] == str(second.id) != str(first.id)
    assert event["reply_id"] == "Sí"


@respx.mock
def test_without_erplora_lifting_it_the_option_is_read_from_meta_s_object(chat, django_capture_on_commit_callbacks):
    question = asked(django_capture_on_commit_callbacks, "wamid.Q1")
    meta = {
        "context": {"from": "34910000000", "id": "wamid.Q1"},
        "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "confirm", "title": "Confirmar"}},
    }
    out = receive("wamid.A1", type="interactive", text="", payload=meta)
    answer = Message.objects.get(pk=out.id)
    assert (answer.reply_to, answer.reply_id, answer.body) == ("wamid.Q1", "confirm", "Confirmar")
    assert received_event(out.id)["reply_to_message_id"] == str(question.id)
    # A template's quick reply comes as a «button» with its payload.
    button = {"context": {"id": "wamid.Q1"}, "type": "button", "button": {"payload": "Sí", "text": "Sí"}}
    out = receive("wamid.A2", type="button", text="", payload=button)
    assert (Message.objects.get(pk=out.id).reply_id, Message.objects.get(pk=out.id).body) == ("Sí", "Sí")


def test_a_reply_to_nothing_this_hub_sent_leaves_both_empty_never_absent(chat):
    out = receive("wamid.A1", type="button", text="Sí", reply_to="wamid.OTHER_HUB", reply={"id": "yes", "title": "Sí"})
    event = received_event(out.id)
    assert event["reply_to_message_id"] is None and event["reply_id"] == "yes"
    plain = receive("wamid.TEXT", text="Hola otra vez")
    event = received_event(plain.id)
    assert {"reply_to_message_id", "reply_id"} <= event.keys()
    assert (event["reply_to_message_id"], event["reply_id"]) == (None, "")


def test_quoting_her_own_message_answers_nothing_the_hub_asked(chat):
    """WhatsApp lets her quote her own «wamid.HELLO»: that is not an answer to a question of the Hub."""
    out = receive("wamid.A1", text="Lo de antes", reply_to="wamid.HELLO")
    assert Message.objects.get(pk=out.id).reply_to == "wamid.HELLO"
    assert received_event(out.id)["reply_to_message_id"] is None


@respx.mock
def test_erasing_the_number_forgets_what_she_tapped(chat, django_capture_on_commit_callbacks):
    asked(django_capture_on_commit_callbacks, "wamid.Q1")
    out = receive("wamid.A1", type="button", text="Sí", reply_to="wamid.Q1", reply={"id": "confirm", "title": "Sí"})
    run("whatsapp_inbox.conversation.erase", {"conversation": "+34600111222"})
    assert Message.objects.get(pk=out.id).reply_id == ""
