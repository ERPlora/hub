"""What the inbox gives its automatic answers (WHATSAPP_INBOX-F20, F21, F24): the message that started them, read by
its id, and the «Needs attention» mark an answer leaves when it could not answer.

The received message's event says whether it is live or brought from the history, so an answer never starts on an
old chat; the read gives the conversation's exact number and the name to make a card with; the mark keeps the
conversation waiting for an answer (the bell, «Waiting for an answer») after the apology went out, until somebody
of the business answers, from the Hub or from the phone, or changes its status.
"""

import datetime as dt

import pytest
from live.errors import NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, card, connect, ctx_for, receive, run

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")]


def at(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()


def message(wa_id: str = "wamid.1") -> Message:
    return Message.objects.get(wa_message_id=wa_id)


def waiting() -> int:
    return run("whatsapp_inbox.conversation.count_awaiting_reply", {}).count


def flag(conversation: Conversation, ctx=None):
    return run("whatsapp_inbox.conversation.flag", {"id": str(conversation.id)}, ctx)


def answer(conversation: Conversation, text: str = "Te miro la agenda") -> None:
    run(
        "whatsapp_inbox.message.send",
        {"id": str(conversation.id), "text": text, "client_message_id": "0199e000-0000-7000-8000-0000000000f1"},
    )


def notify(text: str = "Perdona, ahora mismo no puedo mirar la agenda.") -> None:
    run("whatsapp_inbox.message.notify", {"phone": "+34600111222", "text": text})


# ── The event says whether the message is live ──────────────────────────────────────────────────────


@pytest.mark.parametrize("source", ["live", "history"])
def test_the_received_event_says_whether_the_message_is_live_or_from_the_history(source):
    receive("wamid.1", source=source)
    [payload] = events("whatsapp_inbox.message.received")
    assert payload["source"] == source
    assert payload["direction"] == "inbound"


# ── whatsapp_inbox.message.get ───────────────────────────────────────────────────────────────────────


def test_the_message_is_read_with_its_conversation_s_exact_number_and_the_name_to_call_her():
    receive("wamid.1", "34600111222", contact_name="Lucía", text="¿Tenéis hueco el lunes para un corte?")
    read = run("whatsapp_inbox.message.get", {"id": str(message().id)})
    conversation = Conversation.objects.get()
    assert (read.id, read.conversation_id, read.phone) == (message().id, conversation.id, "+34600111222")
    assert (read.direction, read.source, read.kind) == ("inbound", "live", "text")
    assert read.body == "¿Tenéis hueco el lunes para un corte?"
    assert read.display_name == "Lucía"


def test_with_no_whatsapp_name_her_number_is_the_name_and_with_a_card_its_name():
    receive("wamid.1", "34600111222", contact_name="")
    assert run("whatsapp_inbox.message.get", {"id": str(message().id)}).display_name == "+34600111222"
    card("Lucía Pérez", "600111222")
    receive("wamid.2", "34600111222", contact_name="Lu")
    assert run("whatsapp_inbox.message.get", {"id": str(message("wamid.2").id)}).display_name == "Lucía Pérez"


def test_it_says_whether_anything_can_be_sent_now():
    receive("wamid.1")
    assert run("whatsapp_inbox.message.get", {"id": str(message().id)}).can_send is False  # no number connected yet
    connect()
    assert run("whatsapp_inbox.message.get", {"id": str(message().id)}).can_send is True
    connect(version=2, monthly_usage=150)  # the month's 150 spent
    assert run("whatsapp_inbox.message.get", {"id": str(message().id)}).can_send is False


def test_a_message_of_an_erased_conversation_or_of_nobody_is_not_found():
    receive("wamid.1")
    found = message()
    run("whatsapp_inbox.conversation.erase", {"id": str(found.conversation_id)})
    with pytest.raises(NotFound):
        run("whatsapp_inbox.message.get", {"id": str(found.id)})
    with pytest.raises(NotFound):
        run("whatsapp_inbox.message.get", {"id": "0199e000-0000-7000-8000-0000000000aa"})


def test_reading_a_message_needs_the_inbox():
    receive("wamid.1")
    with pytest.raises(PermissionDenied):
        run("whatsapp_inbox.message.get", {"id": str(message().id)}, ctx_for("hub_viewer_without_inbox"))


# ── The options last offered to her (WHATSAPP_INBOX-F19) ──────────────────────────────────────────────

OFFERED = "1. Saturday at 20:00\n2. Saturday at 21:30"


def options(wa_id: str) -> str:
    return run("whatsapp_inbox.message.get", {"id": str(message(wa_id).id)}).options


def test_her_answer_comes_with_the_options_the_business_last_wrote_her():
    connect()
    receive("wamid.1", "34600111222", text="A table for 4 on Saturday")
    notify("Thanks for writing!")
    notify(OFFERED)
    receive("wamid.2", "34600111222", text="the 2nd")
    assert options("wamid.2") == OFFERED
    assert options("wamid.1") == ""  # what was written after a message is not what it answers


def test_once_the_business_writes_again_the_list_is_forgotten():
    connect()
    receive("wamid.1", "34600111222", text="A table for 4 on Saturday")
    notify(OFFERED)
    notify("Booked: Saturday at 21:30, 4 guests.")
    receive("wamid.2", "34600111222", text="Thanks!")
    assert options("wamid.2") == "Booked: Saturday at 21:30, 4 guests."


def test_options_older_than_24_hours_are_forgotten():
    connect()
    receive("wamid.1", "34600111222", text="A table for 4 on Saturday")
    notify(OFFERED)
    receive("wamid.2", "34600111222", text="the 2nd")
    answer_at = message("wamid.2").created_at
    offer = Message.objects.filter(direction="outbound")
    offer.update(created_at=answer_at - dt.timedelta(hours=24, seconds=1))
    assert options("wamid.2") == ""
    offer.update(created_at=answer_at - dt.timedelta(hours=23, minutes=59))
    assert options("wamid.2") == OFFERED


def test_only_what_the_hub_got_to_send_her_counts():
    connect()
    receive("wamid.1", "34600111222", text="A table for 4 on Saturday")
    receive("wamid.0", "34600999999", text="Hi")
    notify(OFFERED)
    run("whatsapp_inbox.message.notify", {"phone": "+34600999999", "text": "1. Another guest's time"})
    Message.objects.create(  # a message the Hub sent her that never got there
        conversation=Conversation.objects.get(phone="+34600111222"),
        direction="outbound",
        origin="hub",
        body="1. A list that failed",
        status="failed",
        sent_at=NOW,
    )
    receive("wamid.echo", "34600111222", direction="outbound", text="I call you now", contact_name="")  # her phone
    receive("wamid.2", "34600111222", text="the 2nd")
    assert options("wamid.2") == OFFERED



# ── whatsapp_inbox.conversation.flag (WHATSAPP_INBOX-F20) ───────────────────────────────────────────


def test_a_flagged_conversation_keeps_waiting_for_an_answer_after_the_apology_went_out():
    connect()
    receive("wamid.1", sent_at=at(1))
    conversation = Conversation.objects.get()
    notify()
    assert waiting() == 0  # the apology is the business's last message
    flagged = flag(conversation)
    assert (flagged.id, flagged.flagged) == (conversation.id, True)
    assert waiting() == 1
    assert run("whatsapp_inbox.conversation.summary", {}).awaiting_reply == 1
    assert run("whatsapp_inbox.conversation.detail", {"id": str(conversation.id)}).flagged is True
    [row] = run("whatsapp_inbox.conversation.list", {}).rows
    assert row.flagged is True
    assert events("whatsapp_inbox.conversation.flagged") == [{"id": str(conversation.id)}]


def test_flagging_twice_is_one_mark_and_one_event():
    receive("wamid.1")
    conversation = Conversation.objects.get()
    flag(conversation)
    flag(conversation)
    assert len(events("whatsapp_inbox.conversation.flagged")) == 1


def test_an_answer_from_the_hub_takes_the_mark_away():
    connect()
    receive("wamid.1", sent_at=at(1))
    conversation = Conversation.objects.get()
    flag(conversation)
    answer(conversation)
    assert Conversation.objects.get().needs_attention is False
    assert waiting() == 0


def test_an_answer_from_the_business_s_phone_takes_the_mark_away():
    receive("wamid.1", sent_at=at(2))
    flag(Conversation.objects.get())
    receive("wamid.echo", direction="outbound", text="Te llamo ahora", contact_name="", sent_at=at(1))
    assert Conversation.objects.get().needs_attention is False
    assert waiting() == 0


def test_another_automatic_message_leaves_the_mark_on():
    connect()
    receive("wamid.1", sent_at=at(1))
    flag(Conversation.objects.get())
    notify("Otro aviso")
    assert Conversation.objects.get().needs_attention is True
    assert waiting() == 1


@pytest.mark.parametrize("status", ["pending", "closed"])
def test_changing_its_status_takes_the_mark_away(status):
    receive("wamid.1")
    conversation = Conversation.objects.get()
    flag(conversation)
    run("whatsapp_inbox.conversation.set_status", {"id": str(conversation.id), "status": status})
    assert Conversation.objects.get().needs_attention is False


def test_a_closed_or_erased_conversation_is_not_flagged():
    receive("wamid.1")
    conversation = Conversation.objects.get()
    run("whatsapp_inbox.conversation.set_status", {"id": str(conversation.id), "status": "closed"})
    assert flag(conversation).flagged is False
    run("whatsapp_inbox.conversation.erase", {"id": str(conversation.id)})
    with pytest.raises(NotFound):
        flag(conversation)
    assert events("whatsapp_inbox.conversation.flagged") == []


def test_flagging_needs_whoever_may_answer():
    receive("wamid.1")
    with pytest.raises(PermissionDenied):
        flag(Conversation.objects.get(), ctx_for("hub_viewer_without_inbox"))
