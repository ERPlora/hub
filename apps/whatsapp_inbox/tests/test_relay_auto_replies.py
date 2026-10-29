"""«The customer asks for an appointment by WhatsApp» and «… for a table» (WHATSAPP_INBOX-F20, F21, F24), end to end
through the worker's real outbox relay, Automatizaciones' engine and erplora.com's doors.

erplora.com is ``base.tests.fake_gateway`` on 127.0.0.1: its assistant door (``/internal/assistant/chat``) answers
each turn as scripted and its WhatsApp door (``/internal/whatsapp/send``) takes each message, both called by the Hub's
real network code. The inbox's automatic answer is turned on as the owner does it; the customer's message comes in
through the inbox's own door; one tick of the worker hands its event to Automatizaciones, whose run reads the message,
thanks her, makes her card and asks the assistant with only what the answer was granted. «Ask me first»: the booking
it wants waits in «Waiting for your answer»; the owner's yes runs Citas' (or Reservas') real operation, whose answer
goes back to the assistant, and what the assistant says then goes to her (Reservas books the table or the waiting
list; Citas, today, refuses a booking made for a professional by an automation). When the assistant fails, she gets the apology and her conversation stays
waiting for an answer, marked «Needs attention».
"""

import datetime as dt
import json
import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

from apps.appointment.models import Appointment
from apps.appointment.tests.conftest import MONDAY, anytime, assign, make_member, make_service, wall  # noqa: F401
from apps.customer.models import Customer
from apps.flow.models import FlowRun, Question
from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.tests.conftest import open_week, set_rules
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, connect, ctx_for, receive, run
from base import catalog, worker
from base.catalog import RegisterResult
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]

CHAT = "/internal/assistant/chat"
SEND = "/internal/whatsapp/send"
QUOTA = {"used": 1, "limit": 300, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
BOOKING_REF = "whatsapp_inbox/appointment_from_whatsapp"
TABLE_REF = "whatsapp_inbox/reservation_from_whatsapp"
LUCIA = "+34600111222"
THANKS = "Thanks for writing! Let me check the diary and I will come straight back to you."
SORRY = "Sorry, I cannot check the diary right now. Someone from the team will answer you here as soon as they can."


@pytest.fixture
def tick(monkeypatch, django_capture_on_commit_callbacks):
    """One turn of the worker's real loop (``test_relay_notify.py``'s): the relay, then what each COMMIT left for
    after it (the deliveries to erplora.com, the assistant's turns)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def run_once() -> None:
        stop = threading.Event()
        now = timezone.now()

        def wait(seconds: float) -> bool:
            stop.set()
            return True

        with django_capture_on_commit_callbacks(execute=True):
            assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now + dt.timedelta(seconds=1)) == 0

    return run_once


def said(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA}


def wants(name: str, arguments: dict) -> dict:
    call = {"type": "function_call", "call_id": "call_1", "name": name.replace(".", "__"), "arguments": json.dumps(arguments)}
    return {"output": [call], "continuation": "token-1", "quota": QUOTA}


def door_takes(gateway, times: int) -> None:  # noqa: F811 - the fixture
    for number in range(times):
        gateway.reply(SEND, json={"wa_message_id": f"wamid.OUT{number}"})


def outbound() -> list[str]:
    return list(Message.objects.filter(direction="outbound").order_by("created_at", "id").values_list("body", flat=True))


def offered(seen) -> list[str]:
    return [tool["name"] for tool in seen.body["tools"]]


def answer_yes(django_capture_on_commit_callbacks) -> Question:
    question = Question.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        run("flow.question.answer", {"id": str(question.id), "approve": True}, ctx_for("hub_owner"))
    return question


def salon():
    """The owner's salon: its number connected, a haircut Ana performs and the answer turned on."""
    connect()
    cut = make_service("Haircut", price=2000, duration=30)
    ana = make_member("Ana", "López")
    assign(cut, ana)
    run("flow.recipe.enable", {"recipe": BOOKING_REF}, ctx_for("hub_owner"))
    return cut, ana


def lucia_writes(text: str = "¿Tenéis hueco el lunes a las 10 para un corte?", **fields) -> None:
    receive("wamid.IN", "34600111222", contact_name="Lucía", text=text, sent_at=NOW.isoformat(), **fields)


def test_she_asks_for_an_appointment_the_booking_waits_for_the_owner_s_yes_and_then_she_is_told(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    cut, ana = salon()
    door_takes(gateway, 2)
    booking = {
        "customer": LUCIA,
        "services": [{"service_id": str(cut.id)}],
        "staff_id": str(ana.id),
        "start": wall(MONDAY, "10:00"),
        "source": "whatsapp",
    }
    gateway.reply(CHAT, json=wants("appointment.appointment.create", booking))
    gateway.reply(CHAT, json=said("¡Hecho! Te espero el lunes a las 10:00 con Ana."))
    lucia_writes()

    tick()

    # The thanks went at once; her card was made from WhatsApp; the booking waits for the owner's yes.
    assert outbound() == [THANKS]
    card = Customer.objects.get()
    assert (card.name, card.phone, card.source) == ("Lucía", LUCIA, "whatsapp")
    [asked] = gateway.sent(CHAT)
    assert signed(asked)
    prompt = asked.body["messages"][0]["content"]
    assert "\n———\n¿Tenéis hueco el lunes a las 10 para un corte?\n———\n" in prompt  # her words alone on their lines
    assert LUCIA in prompt and str(card.id) in prompt
    assert offered(asked) == [
        "appointment__availability__slots",
        "appointment__appointment__create",
        "appointment__appointment__reschedule",
    ]
    assert Appointment.objects.count() == 0
    assert FlowRun.objects.get().status == FlowRun.Status.ASKING
    question = Question.objects.get()
    assert "Customer: +34600111222" in question.details  # the owner sees for whom before saying yes

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    # The yes takes the step back to the assistant with what Citas answered to the booking, and what it says then is
    # the WhatsApp she gets: never left without an answer.
    first, second = gateway.sent(CHAT)
    told = second.body["messages"][-1]
    assert (told["role"], told["tool_call_id"]) == ("tool", "call_1")
    assert outbound() == [THANKS, "¡Hecho! Te espero el lunes a las 10:00 con Ana."]
    assert [json.loads(seen.raw)["to"] for seen in gateway.sent(SEND)] == [LUCIA, LUCIA]
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED
    assert Conversation.objects.get().needs_attention is False


def test_a_customer_with_a_card_is_booked_on_it_and_no_other_card_is_made(gateway, tick):  # noqa: F811
    salon()
    door_takes(gateway, 2)
    mine = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    gateway.reply(CHAT, json=said("¿Te va bien el lunes a las 10:00 o a las 11:30?"))
    lucia_writes("Quiero cita el lunes")

    tick()

    assert Customer.objects.count() == 1
    [asked] = gateway.sent(CHAT)
    assert str(mine.id) in asked.body["messages"][0]["content"]
    assert outbound() == [THANKS, "¿Te va bien el lunes a las 10:00 o a las 11:30?"]
    assert Question.objects.count() == 0  # a read and an answer: nothing waits for the owner


def test_when_the_assistant_fails_she_gets_the_apology_and_her_conversation_needs_attention(gateway, tick):  # noqa: F811
    salon()
    door_takes(gateway, 2)
    gateway.reply(CHAT, status=429, json={"error": {"code": "assistant.quota_exceeded", "message": "x", "retriable": False}})
    lucia_writes()

    tick()

    assert outbound() == [THANKS, SORRY]
    assert Conversation.objects.get().needs_attention is True
    assert run("whatsapp_inbox.conversation.count_awaiting_reply", {}).count == 1
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


def test_when_the_assistant_says_nothing_she_gets_the_apology_too(gateway, tick):  # noqa: F811
    salon()
    door_takes(gateway, 2)
    gateway.reply(CHAT, json=said(""))
    lucia_writes()

    tick()

    assert outbound() == [THANKS, SORRY]
    assert Conversation.objects.get().needs_attention is True


def test_with_the_month_s_messages_spent_nothing_goes_nothing_is_asked_and_she_waits_marked(gateway, tick):  # noqa: F811
    salon()
    connect(version=2, monthly_usage=150)
    lucia_writes()

    tick()

    assert outbound() == []
    assert gateway.sent(CHAT) == [] and gateway.sent(SEND) == []
    assert Conversation.objects.get().needs_attention is True
    assert Customer.objects.count() == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"direction": "outbound", "text": "Te llamo ahora", "contact_name": ""},  # the owner, from her phone
        {"source": "history"},  # an old chat connecting the number brought
        {"type": "image", "text": "", "media": {"url": "https://erplora.com/m/1", "mime_type": "image/jpeg"}},
    ],
)
def test_an_echo_an_old_chat_or_a_photo_without_text_gets_no_answer(gateway, tick, fields):  # noqa: F811
    salon()
    receive("wamid.IN", "34600111222", **{"contact_name": "Lucía", "text": "Hola", "sent_at": NOW.isoformat(), **fields})

    tick()

    assert gateway.sent(CHAT) == [] and gateway.sent(SEND) == []
    assert outbound() == ([] if fields.get("direction") != "outbound" else ["Te llamo ahora"])


def test_a_guest_asks_for_a_table_and_after_the_owner_s_yes_it_is_booked_with_their_number(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    connect()
    open_week()
    set_rules(auto_confirm=True)
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)  # Reservas reads the real calendar
    gateway.reply(
        CHAT,
        json=wants(
            "reservation.reservation.create",
            {
                "customer_id": str(card.id),
                "guest_name": "Lucía",
                "guest_phone": LUCIA,
                "date": day.isoformat(),
                "time": "21:00",
                "party_size": 4,
                "source": "whatsapp",
            },
        ),
    )
    gateway.reply(CHAT, json=said("¡Listo! Mesa para 4 el sábado a las 21:00."))
    lucia_writes("Mesa para 4 el sábado a las 21")

    tick()

    assert outbound() == ["Thanks for writing! Let me check the reservations book and I will come straight back to you."]
    [asked] = gateway.sent(CHAT)
    assert offered(asked) == [
        "reservation__availability__day",
        "reservation__availability__tables",
        "reservation__reservation__create",
        "reservation__reservation__update",
        "reservation__waitlist__create",
    ]
    assert Reservation.objects.count() == 0

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    reservation = Reservation.objects.get()
    assert (reservation.customer_id, reservation.guest_phone, reservation.party_size, reservation.source) == (
        card.id, LUCIA, 4, "whatsapp"
    )
    assert str(card.id) in gateway.sent(CHAT)[0].body["messages"][0]["content"]
    assert Customer.objects.count() == 1
    assert outbound()[-1] == "¡Listo! Mesa para 4 el sábado a las 21:00."
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


def test_with_no_room_the_guest_is_written_on_the_waiting_list_after_the_owner_s_yes(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    gateway.reply(
        CHAT,
        json=wants(
            "reservation.waitlist.create",
            {
                "customer_id": str(card.id),
                "guest_name": "Lucía",
                "guest_phone": LUCIA,
                "date": day.isoformat(),
                "preferred_time": "21:00",
                "party_size": 4,
            },
        ),
    )
    gateway.reply(CHAT, json=said("Te he apuntado en la lista de espera para el sábado a las 21:00."))
    lucia_writes("Mesa para 4 el sábado a las 21")

    tick()
    assert WaitlistEntry.objects.count() == 0  # it waits for the owner's yes

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    entry = WaitlistEntry.objects.get()
    assert (entry.customer_id, entry.guest_phone, entry.party_size) == (card.id, LUCIA, 4)
    assert outbound()[-1] == "Te he apuntado en la lista de espera para el sábado a las 21:00."
