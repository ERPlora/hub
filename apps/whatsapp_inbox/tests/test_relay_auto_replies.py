"""«The guest asks for a table by WhatsApp» (WHATSAPP_INBOX-F20, F24, F25) and «… for an appointment» (F21, F22), end to
end through the worker's real outbox relay, Automatizaciones' engine and erplora.com's doors.

erplora.com is ``base.tests.fake_gateway`` on 127.0.0.1: its assistant door (``/internal/assistant/chat``) answers
each turn as scripted and its WhatsApp door (``/internal/whatsapp/send``) takes each message, both called by the Hub's
real network code. The inbox's automatic answer is turned on as the owner does it; the guest's message comes in
through the inbox's own door; one tick of the worker hands its event to Automatizaciones, whose run reads the message,
thanks them, makes their card and asks the assistant with only what the answer was granted. «Ask me first»: the booking
it wants waits in «Waiting for your answer»; the owner's yes runs Reservas' (or Citas') real operation, whose answer goes
back to the assistant, and what the assistant says then goes to them. A cancellation too (F22, F25), only of their own
booking: each app refuses any other on their behalf. When the assistant fails, they get the apology and their
conversation stays waiting for an answer, marked «Needs attention».
"""

import datetime as dt
import json
import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

from apps.appointment.models import Appointment
from apps.appointment.tests.conftest import (  # noqa: F401 - anytime is a fixture
    MONDAY,
    anytime,
    assign,
    at,
    make_appointment,
    make_member,
    make_service,
    make_settings,
    next_weekday,
    wall,
)
from apps.customer.models import Customer
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import TURN
from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.tests.conftest import make_reservation, open_week, set_rules
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, connect, ctx_for, receive, run
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import TaskSchedule
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

CHAT = "/internal/assistant/chat"
SEND = "/internal/whatsapp/send"
QUOTA = {"used": 1, "limit": 300, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
TABLE_REF = "whatsapp_inbox/reservation_from_whatsapp"
BOOKING_REF = "whatsapp_inbox/appointment_from_whatsapp"
LUCIA = "+34600111222"
THANKS = "Thanks for writing! Let me check the reservations book and I will come straight back to you."
SORRY = (
    "Sorry, I cannot check the reservations right now. Someone from the team will answer you here as soon as they can."
)


@pytest.fixture
def tick(monkeypatch, django_capture_on_commit_callbacks):
    """One turn of the worker's real loop (``test_relay_notify.py``'s): the tasks due and the relay, then what each
    COMMIT left for after it (the deliveries to erplora.com, the assistant's turns). ``tick(later)`` runs it with its
    clock ``later`` than now (a second by default)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def run_once(later: dt.timedelta = dt.timedelta(seconds=1)) -> None:
        stop = threading.Event()
        now = timezone.now()

        def wait(seconds: float) -> bool:
            stop.set()
            return True

        with django_capture_on_commit_callbacks(execute=True):
            assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now + later) == 0

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


def restaurant() -> None:
    """The owner's restaurant: its number connected, its week open and the answer turned on."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))


def lucia_writes(text: str = "Mesa para 4 el sábado a las 21", **fields) -> None:
    receive("wamid.IN", "34600111222", contact_name="Lucía", text=text, sent_at=NOW.isoformat(), **fields)


def test_a_guest_with_no_card_gets_one_from_whatsapp_and_the_assistant_hears_their_words_alone(gateway, tick):  # noqa: F811
    restaurant()
    door_takes(gateway, 2)
    gateway.reply(CHAT, json=said("¿Para cuántas personas?"))
    lucia_writes()

    tick()

    card = Customer.objects.get()
    assert (card.name, card.phone, card.source) == ("Lucía", LUCIA, "whatsapp")
    [asked] = gateway.sent(CHAT)
    assert signed(asked)
    prompt = asked.body["messages"][0]["content"]
    assert "\n———\nMesa para 4 el sábado a las 21\n———\n" in prompt  # their words alone on their lines
    assert LUCIA in prompt and str(card.id) not in prompt  # their card is fixed on a booking, never told
    assert outbound() == [THANKS, "¿Para cuántas personas?"]


def test_a_guest_with_a_card_is_booked_on_it_and_no_other_card_is_made(gateway, tick):  # noqa: F811
    restaurant()
    door_takes(gateway, 2)
    mine = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    gateway.reply(CHAT, json=said("¿Os va bien a las 21:00 o a las 22:30?"))
    lucia_writes("Quiero mesa el sábado")

    tick()

    assert Customer.objects.count() == 1
    [asked] = gateway.sent(CHAT)
    assert str(mine.id) not in asked.body["messages"][0]["content"]  # fixed on a booking, never told
    assert outbound() == [THANKS, "¿Os va bien a las 21:00 o a las 22:30?"]
    assert Question.objects.count() == 0  # a read and an answer: nothing waits for the owner


def test_when_the_assistant_fails_they_get_the_apology_and_their_conversation_needs_attention(gateway, tick):  # noqa: F811
    restaurant()
    door_takes(gateway, 2)
    gateway.reply(CHAT, status=429, json={"error": {"code": "assistant.quota_exceeded", "message": "x", "retriable": False}})
    lucia_writes()

    tick()

    assert outbound() == [THANKS, SORRY]
    assert Conversation.objects.get().needs_attention is True
    assert run("whatsapp_inbox.conversation.count_awaiting_reply", {}).count == 1
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


def test_when_the_assistant_says_nothing_they_get_the_apology_too(gateway, tick):  # noqa: F811
    restaurant()
    door_takes(gateway, 2)
    gateway.reply(CHAT, json=said(""))
    lucia_writes()

    tick()

    assert outbound() == [THANKS, SORRY]
    assert Conversation.objects.get().needs_attention is True


def test_with_the_month_s_messages_spent_nothing_goes_nothing_is_asked_and_they_wait_marked(gateway, tick):  # noqa: F811
    restaurant()
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
    restaurant()
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

    assert outbound() == [THANKS]
    [asked] = gateway.sent(CHAT)
    assert offered(asked) == [
        "reservation__availability__day",
        "reservation__availability__tables",
        "reservation__reservation__create",
        "reservation__reservation__update",
        "reservation__reservation__cancel",
        "reservation__waitlist__create",
    ]
    assert Reservation.objects.count() == 0

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    reservation = Reservation.objects.get()
    assert (reservation.customer_id, reservation.guest_phone, reservation.party_size, reservation.source) == (
        card.id, LUCIA, 4, "whatsapp"
    )
    assert str(card.id) not in gateway.sent(CHAT)[0].body["messages"][0]["content"]  # fixed by the answer, never told
    assert Customer.objects.count() == 1
    assert outbound()[-1] == "¡Listo! Mesa para 4 el sábado a las 21:00."
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


def test_a_guest_who_answers_the_2nd_of_the_times_offered_is_booked_at_it_after_the_owner_s_yes(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F19: with no room at the time asked, the assistant offers a short numbered list; when the guest then writes «el 2»,
    the assistant hears that list again (what the business last wrote them, between its two lines), so it books the 2nd
    after the owner's yes instead of asking again."""
    restaurant()
    door_takes(gateway, 4)
    day = timezone.localdate() + dt.timedelta(days=3)
    offer = "No hay mesa a las 21:00. Tengo:\n1. Sábado a las 20:00\n2. Sábado a las 21:30"
    gateway.reply(CHAT, json=said(offer))
    gateway.reply(
        CHAT,
        json=wants(
            "reservation.reservation.create",
            {"guest_name": "Lucía", "date": day.isoformat(), "time": "21:30", "party_size": 4, "source": "whatsapp"},
        ),
    )
    gateway.reply(CHAT, json=said("¡Listo! Mesa para 4 el sábado a las 21:30."))
    lucia_writes("Mesa para 4 el sábado a las 21")
    tick()
    assert outbound() == [THANKS, offer]

    receive("wamid.IN2", "34600111222", contact_name="Lucía", text="el 2", sent_at=NOW.isoformat())
    tick()

    first, second = gateway.sent(CHAT)
    assert "\n———\n\n———\n" in first.body["messages"][0]["content"]  # nothing was offered before her first message
    prompt = second.body["messages"][0]["content"]
    assert "\n———\nel 2\n———\n" in prompt
    assert f"\n———\n{offer}\n———\n" in prompt  # the list she answers, on its own lines
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    reservation = Reservation.objects.get()
    assert (reservation.date, reservation.time, reservation.guest_phone) == (day, dt.time(21, 30), LUCIA)
    assert outbound()[-1] == "¡Listo! Mesa para 4 el sábado a las 21:30."


def test_a_guest_with_no_card_is_booked_on_the_card_whatsapp_made_for_them(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F24: with no card of their number, the one the answer makes (``steps.s7.id``) is the card it fixes on the booking,
    which the assistant never names."""
    restaurant()
    door_takes(gateway, 2)
    day = timezone.localdate() + dt.timedelta(days=3)
    gateway.reply(
        CHAT,
        json=wants(
            "reservation.reservation.create",
            {"guest_name": "Lucía", "guest_phone": LUCIA, "date": day.isoformat(), "time": "21:00", "party_size": 4, "source": "whatsapp"},
        ),
    )
    gateway.reply(CHAT, json=said("¡Listo! Mesa para 4 el sábado a las 21:00."))
    lucia_writes()

    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    card = Customer.objects.get()
    assert (card.phone, card.source) == (LUCIA, "whatsapp")
    assert Reservation.objects.get().customer_id == card.id


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


def test_a_guest_moves_their_table_and_after_the_owner_s_yes_it_is_at_the_new_time(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    booked = make_reservation(date=day, time="21:00", customer_id=card.id, guest_name="Lucía", guest_phone=LUCIA, party_size=4)
    gateway.reply(CHAT, json=wants("reservation.reservation.update", {"id": str(booked.id), "time": "22:00"}))
    gateway.reply(CHAT, json=said("Hecho: os esperamos el sábado a las 22:00."))
    lucia_writes("¿Podemos pasarla a las 22?")

    tick()
    booked.refresh_from_db()
    assert booked.time == dt.time(21, 0)  # it waits for the owner's yes
    assert str(booked.id) in gateway.sent(CHAT)[0].body["messages"][0]["content"]  # her latest, read before

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    booked.refresh_from_db()
    assert booked.time == dt.time(22, 0)
    assert outbound()[-1] == "Hecho: os esperamos el sábado a las 22:00."


def test_a_guest_cancels_their_table_and_after_the_owner_s_yes_it_is_cancelled(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F25: the cancellation of their latest reservation, read before by their number, waits for a yes; with it,
    Reservas cancels it on their behalf and what the assistant says then goes to them."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    booked = make_reservation(date=day, time="21:00", customer_id=card.id, guest_name="Lucía", guest_phone=LUCIA, party_size=4)
    gateway.reply(
        CHAT,
        json=wants(
            "reservation.reservation.cancel",
            {"id": str(booked.id), "on_behalf_of": str(card.id), "reason": "The guest asked by WhatsApp"},
        ),
    )
    gateway.reply(CHAT, json=said("Hecho: tu reserva del sábado a las 21:00 queda anulada."))
    lucia_writes("Quiero anular mi reserva")

    tick()

    [asked] = gateway.sent(CHAT)
    assert "reservation__reservation__cancel" in offered(asked)
    assert str(booked.id) in asked.body["messages"][0]["content"]  # her latest, read before
    booked.refresh_from_db()
    assert booked.status != Reservation.Status.CANCELLED  # it waits for the yes
    assert Question.objects.count() == 1
    assert outbound() == [THANKS]

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    booked.refresh_from_db()
    assert (booked.status, booked.cancellation_reason) == (Reservation.Status.CANCELLED, "The guest asked by WhatsApp")
    assert outbound()[-1] == "Hecho: tu reserva del sábado a las 21:00 queda anulada."
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


@pytest.mark.parametrize(
    "later", [dt.timedelta(seconds=1), dt.timedelta(minutes=2)], ids=["at_once", "past_the_minute"]
)
def test_the_answer_never_cancels_the_reservation_of_another_number(
    gateway, tick, django_capture_on_commit_callbacks, later  # noqa: F811 - the fixture
):
    """reservations#50: on their behalf, another guest's reservation is refused even after the yes, saying nothing of it;
    the assistant hears the refusal and what it says then goes to them.

    ``past_the_minute``: the tick after the yes lands on another minute than the first one, as in the CI run that got
    the thanks last (18:06:59.147 + 1 s); what the guest gets never depends on the minute it lands on."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    other = run("customer.customer.create", {"name": "Marta Ruiz", "phone": "600999888"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    theirs = make_reservation(
        date=day, time="21:00", customer_id=other.id, guest_name="Marta", guest_phone="+34600999888", party_size=2
    )
    gateway.reply(CHAT, json=wants("reservation.reservation.cancel", {"id": str(theirs.id), "on_behalf_of": str(card.id)}))
    gateway.reply(CHAT, json=said("No encuentro ninguna reserva a tu nombre."))
    lucia_writes("Anula la reserva de Marta del sábado")

    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick(later)

    theirs.refresh_from_db()
    assert theirs.status != Reservation.Status.CANCELLED
    told = [message for message in gateway.sent(CHAT)[-1].body["messages"] if message.get("role") == "tool"]
    assert "reservation.customer_mismatch" in json.dumps(told)
    assert outbound()[-1] == "No encuentro ninguna reserva a tu nombre."
    assert [seen.body["hub"] for seen in gateway.sent(CHAT)] == ["a", "a"]  # both turns, the business's own


def test_a_tick_past_the_minute_runs_the_minute_s_tasks(tick):
    """What ``past_the_minute`` stands on: that tick does run ``flow.run.resume_due``, or the test above measures
    nothing of the minute it lands on (hub#625)."""
    tick()
    tick(dt.timedelta(minutes=2))

    assert TaskSchedule.objects.get(app_label="flow", name="resume_due").last_run is not None


def tool_inputs(seen, name: str) -> set[str]:
    [tool] = [tool for tool in seen.body["tools"] if tool["name"] == name.replace(".", "__")]
    return set(tool["parameters"].get("properties", {}))


@pytest.mark.parametrize("naming", ["by_id", "by_id_on_marta_s_behalf", "by_her_name_and_day"])
@pytest.mark.parametrize(
    ("tool", "change"),
    [("reservation.reservation.cancel", {}), ("reservation.reservation.update", {"time": "22:00"})],
    ids=["cancel", "update"],
)
def test_the_answer_never_cancels_or_changes_another_guest_s_reservation_whatever_the_assistant_sends(
    gateway, tick, django_capture_on_commit_callbacks, tool, change, naming  # noqa: F811 - the fixture
):
    """F25: whose card a change goes on is fixed by the answer to the card of the number that writes, never asked of
    the assistant (FLOW-F38). Lucía asks to cancel or move Marta's table and the assistant names it by its id or by
    Marta's name and day, saying nothing of on whose behalf or saying Marta's: after the yes, Marta's reservation is as
    it was and the assistant hears Reservas' refusal."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    marta = run("customer.customer.create", {"name": "Marta Ruiz", "phone": "600999888"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    theirs = make_reservation(
        date=day, time="21:00", customer_id=marta.id, guest_name="Marta Ruiz", guest_phone="+34600999888", party_size=2
    )
    sent = {
        "by_id": {"id": str(theirs.id)},
        "by_id_on_marta_s_behalf": {"id": str(theirs.id), "on_behalf_of": str(marta.id)},
        "by_her_name_and_day": {"guest": "Marta Ruiz", "day": day.isoformat()},
    }[naming] | change
    gateway.reply(CHAT, json=wants(tool, sent))
    gateway.reply(CHAT, json=said("No encuentro ninguna reserva a tu nombre."))
    lucia_writes("Anula la reserva de Marta Ruiz del sábado" if not change else "Pasa la de Marta Ruiz a las 22")

    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    theirs.refresh_from_db()
    assert (theirs.status, theirs.time) == (Reservation.Status.PENDING, dt.time(21, 0))
    told = [message for message in gateway.sent(CHAT)[-1].body["messages"] if message.get("role") == "tool"]
    assert "reservation.customer_mismatch" in json.dumps(told)
    assert outbound()[-1] == "No encuentro ninguna reserva a tu nombre."
    asked = gateway.sent(CHAT)[0]
    assert "on_behalf_of" not in tool_inputs(asked, tool)  # never the assistant's to say
    assert "on_behalf_of" not in asked.body["messages"][0]["content"]


def test_a_guest_cancels_their_own_table_without_the_assistant_saying_on_whose_behalf(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F25: the answer puts their own card in, so their cancellation goes on their behalf with the assistant naming only
    the reservation."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    booked = make_reservation(date=day, time="21:00", customer_id=card.id, guest_name="Lucía", guest_phone=LUCIA, party_size=4)
    gateway.reply(CHAT, json=wants("reservation.reservation.cancel", {"id": str(booked.id)}))
    gateway.reply(CHAT, json=said("Hecho: tu reserva del sábado a las 21:00 queda anulada."))
    lucia_writes("Quiero anular mi reserva")

    tick()
    proposed = json.loads(FlowRun.objects.get().outputs[TURN]["proposal"]["arguments"])
    assert proposed == {"id": str(booked.id), "on_behalf_of": str(card.id)}
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    booked.refresh_from_db()
    assert booked.status == Reservation.Status.CANCELLED
    assert outbound()[-1] == "Hecho: tu reserva del sábado a las 21:00 queda anulada."


@pytest.mark.parametrize("naming", ["by_her_name", "by_her_card"])
@pytest.mark.parametrize(
    ("tool", "booking"),
    [
        ("reservation.reservation.create", {"time": "21:00", "source": "whatsapp"}),
        ("reservation.waitlist.create", {"preferred_time": "21:00"}),
    ],
    ids=["book", "waitlist"],
)
def test_the_answer_never_books_or_waitlists_on_another_guest_s_card_whatever_the_assistant_sends(
    gateway, tick, django_capture_on_commit_callbacks, tool, booking, naming  # noqa: F811 - the fixture
):
    """F24: whose card a booking or a place on the waiting list goes on is fixed by the answer to the card of the
    number that writes, never asked of the assistant (FLOW-F38). The assistant names Marta, by her name or by her card:
    after the yes, it is on Lucía's card and Marta's has nothing."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    marta = run("customer.customer.create", {"name": "Marta Ruiz", "phone": "600999888"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    whose = {"by_her_name": {"customer": "Marta Ruiz"}, "by_her_card": {"customer_id": str(marta.id)}}[naming]
    sent = {**whose, "guest_phone": LUCIA, "date": day.isoformat(), "party_size": 2, **booking}
    gateway.reply(CHAT, json=wants(tool, sent))
    gateway.reply(CHAT, json=said("Hecho."))
    lucia_writes("Mesa para 2 el sábado a las 21 a nombre de Marta Ruiz")

    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    model = Reservation if tool == "reservation.reservation.create" else WaitlistEntry
    made = model.objects.get()
    assert made.customer_id == card.id
    assert not Reservation.objects.filter(customer_id=marta.id).exists()
    assert not WaitlistEntry.objects.filter(customer_id=marta.id).exists()
    assert "customer_id" not in tool_inputs(gateway.sent(CHAT)[0], tool)  # never the assistant's to say


@pytest.mark.parametrize(
    ("tool", "booking"),
    [
        ("reservation.reservation.create", {"time": "21:00", "source": "whatsapp"}),
        ("reservation.waitlist.create", {"preferred_time": "21:00"}),
    ],
    ids=["book", "waitlist"],
)
def test_the_answer_books_and_waitlists_only_with_the_number_that_writes_whatever_the_assistant_sends(
    gateway, tick, django_capture_on_commit_callbacks, tool, booking  # noqa: F811 - the fixture
):
    """F24: the contact phone of a booking or a place on the waiting list is fixed by the answer to the number that
    writes (FLOW-F38): the assistant gives Marta's and, after the yes, it is Lucía's, on Lucía's card."""
    connect()
    open_week()
    run("flow.recipe.enable", {"recipe": TABLE_REF}, ctx_for("hub_owner"))
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    run("customer.customer.create", {"name": "Marta Ruiz", "phone": "600999888"}, ctx_for("hub_owner"))
    day = timezone.localdate() + dt.timedelta(days=3)
    sent = {"customer": "Marta Ruiz", "guest_phone": "+34600999888", "date": day.isoformat(), "party_size": 2, **booking}
    gateway.reply(CHAT, json=wants(tool, sent))
    gateway.reply(CHAT, json=said("Hecho."))
    lucia_writes("Mesa para 2 el sábado a las 21 para Marta Ruiz, su teléfono es el 600 999 888")

    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    model = Reservation if tool == "reservation.reservation.create" else WaitlistEntry
    made = model.objects.get()
    assert (made.customer_id, made.guest_phone) == (card.id, LUCIA)
    assert "guest_phone" not in tool_inputs(gateway.sent(CHAT)[0], tool)  # never the assistant's to say


# ── The customer asks for an appointment by WhatsApp (hub#514; WHATSAPP_INBOX-F14, F21, F22; CUSTOMER-F26) ──────────
#
# The inbox's answer that books appointments, as the owner turns it on: her card and that she herself asks fixed by the
# step, a read at once, and a booking, a move or a cancellation after a yes.

CREATE_APPOINTMENT = "appointment.appointment.create"
RESCHEDULE_APPOINTMENT = "appointment.appointment.reschedule"
CANCEL_APPOINTMENT = "appointment.appointment.cancel"
SLOTS = "appointment.availability.slots"
DIARY_THANKS = "Thanks for writing! Let me check the diary and I will come straight back to you."
DIARY_SORRY = "Sorry, I cannot check the diary right now. Someone from the team will answer you here as soon as they can."


def salon():
    """The owner's salon: its number connected, a haircut Ana performs and the answer turned on."""
    connect()
    cut = make_service("Haircut", price=2000, duration=30)
    ana = make_member("Ana", "López")
    assign(cut, ana)
    run("flow.recipe.enable", {"recipe": BOOKING_REF}, ctx_for("hub_owner"))
    return cut, ana


def booking(cut, ana, start: str = "10:00") -> dict:
    return {"services": [{"service_id": str(cut.id)}], "staff_id": str(ana.id), "start": wall(MONDAY, start)}


def test_she_has_no_card_asks_for_an_appointment_and_after_the_owner_s_yes_it_is_booked_on_the_card_whatsapp_made(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """CUSTOMER-F26, F21: the card is made from WhatsApp before the assistant is asked; the booking waits for the yes with
    whom it is for; on the yes Citas books it for real on that card, pending because the salon reviews first (F16), and
    the WhatsApp she gets is what the assistant says then."""
    cut, ana = salon()
    make_settings(auto_confirm_online=False)
    door_takes(gateway, 2)
    gateway.reply(CHAT, json=wants(CREATE_APPOINTMENT, booking(cut, ana)))
    gateway.reply(CHAT, json=said("¡Apuntada! El salón te confirma el lunes a las 10:00 con Ana."))
    lucia_writes("¿Tenéis hueco el lunes a las 10 para un corte?")

    tick()

    assert outbound() == [DIARY_THANKS]
    card = Customer.objects.get()
    assert (card.name, card.phone, card.source) == ("Lucía", LUCIA, "whatsapp")
    [asked] = gateway.sent(CHAT)
    assert signed(asked)
    prompt = asked.body["messages"][0]["content"]
    assert "\n———\n¿Tenéis hueco el lunes a las 10 para un corte?\n———\n" in prompt  # her words alone on their lines
    assert LUCIA in prompt and str(card.id) not in prompt  # her card is fixed on a booking, never told
    assert offered(asked) == [
        "appointment__availability__slots",
        "appointment__appointment__create",
        "appointment__appointment__reschedule",
        "appointment__appointment__cancel",
    ]
    assert not {"customer_id", "source"} & tool_inputs(asked, CREATE_APPOINTMENT)  # never the assistant's to say
    assert "for_customer" not in tool_inputs(asked, SLOTS)
    assert not {"customer_id", "on_behalf_of_customer"} & tool_inputs(asked, RESCHEDULE_APPOINTMENT)
    assert not {"customer_id", "on_behalf_of_customer"} & tool_inputs(asked, CANCEL_APPOINTMENT)
    assert Appointment.objects.count() == 0
    assert FlowRun.objects.get().status == FlowRun.Status.ASKING
    [waiting] = run("flow.question.list", {}, ctx_for("hub_owner")).rows
    assert waiting.action == "Book an appointment"
    said_values = {field.name: str(field.value) for field in waiting.fields}
    # F21: the owner sees for whom, what and with whom before saying yes, each by its name and never by its id.
    assert "Lucía" in said_values["customer_id"]
    assert "Haircut" in said_values["services"]
    assert "Ana" in said_values["staff_id"]
    assert not any(str(record) in value for record in (card.id, cut.id, ana.id) for value in said_values.values())

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    appointment = Appointment.objects.get()
    assert (appointment.customer_id, appointment.staff_id, appointment.source, appointment.status) == (
        card.id, ana.id, "whatsapp", "pending"
    )
    assert (appointment.customer_phone, appointment.start) == (LUCIA, at(MONDAY, "10:00"))
    assert Customer.objects.count() == 1
    assert outbound() == [DIARY_THANKS, "¡Apuntada! El salón te confirma el lunes a las 10:00 con Ana."]
    assert [json.loads(seen.raw)["to"] for seen in gateway.sent(SEND)] == [LUCIA, LUCIA]
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED
    conversation = Conversation.objects.get()
    assert (conversation.customer_id, conversation.needs_attention) == (card.id, False)


def test_when_the_salon_confirms_by_itself_the_appointment_is_confirmed_on_the_yes(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F16: the salon's rule for the bookings a customer makes herself decides, whatever the assistant sends."""
    cut, ana = salon()
    make_settings(auto_confirm_online=True)
    door_takes(gateway, 2)
    gateway.reply(CHAT, json=wants(CREATE_APPOINTMENT, booking(cut, ana)))
    gateway.reply(CHAT, json=said("¡Reservada! Te espero el lunes a las 10:00 con Ana."))
    lucia_writes("Corte el lunes a las 10")
    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    assert Appointment.objects.get().status == "confirmed"


def test_she_has_a_card_it_is_booked_on_it_and_no_other_card_is_made(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    cut, ana = salon()
    door_takes(gateway, 2)
    mine = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    gateway.reply(CHAT, json=wants(CREATE_APPOINTMENT, booking(cut, ana)))
    gateway.reply(CHAT, json=said("¡Reservada!"))
    lucia_writes("Corte el lunes a las 10")
    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    assert Customer.objects.count() == 1
    assert Appointment.objects.get().customer_id == mine.id
    assert str(mine.id) not in gateway.sent(CHAT)[0].body["messages"][0]["content"]


def test_the_answer_books_only_on_her_card_as_she_would_whatever_the_assistant_sends(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F21: another card named by id or by name, a booking made as if at the counter and an overlap to push through: the
    step's fixed data go over what it sends, and Citas takes the card by its id before any name."""
    cut, ana = salon()
    make_settings(auto_confirm_online=False)
    door_takes(gateway, 2)
    marta = run("customer.customer.create", {"name": "Marta Gil", "phone": "600333444"}, ctx_for("hub_owner"))
    arguments = {**booking(cut, ana), "customer_id": str(marta.id), "customer": "Marta Gil", "source": "counter"}
    gateway.reply(CHAT, json=wants(CREATE_APPOINTMENT, arguments))
    gateway.reply(CHAT, json=said("¡Apuntada!"))
    lucia_writes("Reserva una cita para Marta Gil el lunes a las 10")
    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    appointment = Appointment.objects.get()
    assert appointment.customer_id != marta.id
    assert appointment.customer.phone == LUCIA
    assert (appointment.source, appointment.status) == ("whatsapp", "pending")


def test_the_free_times_she_is_offered_are_a_customer_s_and_nothing_waits_for_the_owner(
    gateway, tick, anytime  # noqa: F811 - the fixture
):
    """F21: a read runs at once and its answer goes back to the assistant, and it is the customer's: inside the salon's
    minimum notice nothing is on offer, whatever the assistant sends."""
    salon()
    make_settings(min_booking_notice=60 * 24 * 365 * 10)
    door_takes(gateway, 2)
    arguments = {"services": ["Haircut"], "date": MONDAY.isoformat(), "for_customer": False}
    gateway.reply(CHAT, json=wants(SLOTS, arguments))
    gateway.reply(CHAT, json=said("Ese día no me quedan huecos."))
    lucia_writes("¿Qué huecos tenéis el lunes?")

    tick()

    told = gateway.sent(CHAT)[1].body["messages"][-1]
    assert told["role"] == "tool"
    assert json.loads(told["content"])["slots"] == []
    assert Question.objects.count() == 0
    assert outbound() == [DIARY_THANKS, "Ese día no me quedan huecos."]


def test_she_answers_the_2nd_of_the_times_offered_and_the_assistant_hears_that_list(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F19: when she writes «el 2», the assistant hears the list again (what the salon last wrote her, on its own lines)."""
    cut, ana = salon()
    door_takes(gateway, 4)
    offer = "Tengo:\n1. Lunes a las 10:00\n2. Lunes a las 11:30"
    gateway.reply(CHAT, json=said(offer))
    gateway.reply(CHAT, json=wants(CREATE_APPOINTMENT, booking(cut, ana, "11:30")))
    gateway.reply(CHAT, json=said("¡Reservada el lunes a las 11:30!"))
    lucia_writes("Quiero cita el lunes")
    tick()
    assert outbound() == [DIARY_THANKS, offer]

    receive("wamid.IN2", "34600111222", contact_name="Lucía", text="el 2", sent_at=NOW.isoformat())
    tick()

    _first, second = gateway.sent(CHAT)
    prompt = second.body["messages"][0]["content"]
    assert "\n———\nel 2\n———\n" in prompt
    assert f"\n———\n{offer}\n———\n" in prompt
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    assert Appointment.objects.get().start == at(MONDAY, "11:30")
    assert outbound()[-1] == "¡Reservada el lunes a las 11:30!"


def test_when_the_assistant_fails_she_gets_the_diary_s_apology_and_her_conversation_needs_attention(
    gateway, tick, anytime  # noqa: F811 - the fixture
):
    salon()
    door_takes(gateway, 2)
    gateway.reply(CHAT, status=429, json={"error": {"code": "assistant.quota_exceeded", "message": "x", "retriable": False}})
    lucia_writes("Quiero cita")

    tick()

    assert outbound() == [DIARY_THANKS, DIARY_SORRY]
    assert Conversation.objects.get().needs_attention is True
    assert Appointment.objects.count() == 0


def test_she_moves_her_appointment_and_after_the_owner_s_yes_it_is_at_the_new_time(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """F22: her latest appointment is read by her card and told to the assistant; the move waits for the yes, and goes
    with the same professional and service, as if she moved it herself."""
    cut, ana = salon()
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    hers = make_appointment(Customer.objects.get(pk=card.id), ana, [cut], at(MONDAY, "10:00"))
    gateway.reply(CHAT, json=wants(RESCHEDULE_APPOINTMENT, {"id": str(hers.id), "start": wall(MONDAY, "12:00")}))
    gateway.reply(CHAT, json=said("Movida al lunes a las 12:00."))
    lucia_writes("¿Me la cambias a las 12?")

    tick()

    assert str(hers.id) in gateway.sent(CHAT)[0].body["messages"][0]["content"]
    hers.refresh_from_db()
    assert hers.start == at(MONDAY, "10:00")  # it waits for the yes
    [waiting] = run("flow.question.list", {}, ctx_for("hub_owner")).rows
    said_values = {field.name: str(field.value) for field in waiting.fields}
    assert "Lucía" in said_values["customer_id"]  # the owner sees whose and which before saying yes
    assert "Ana" in said_values["id"]

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    hers.refresh_from_db()
    assert (hers.start, hers.staff_id) == (at(MONDAY, "12:00"), ana.id)
    assert outbound()[-1] == "Movida al lunes a las 12:00."


def test_the_answer_never_moves_another_customer_s_appointment_even_after_the_yes(
    gateway, tick, anytime, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    cut, ana = salon()
    door_takes(gateway, 2)
    run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    marta = run("customer.customer.create", {"name": "Marta Gil", "phone": "600333444"}, ctx_for("hub_owner"))
    theirs = make_appointment(Customer.objects.get(pk=marta.id), ana, [cut], at(MONDAY, "10:00"))
    arguments = {"id": str(theirs.id), "start": wall(MONDAY, "12:00"), "customer_id": str(marta.id), "on_behalf_of_customer": False}
    gateway.reply(CHAT, json=wants(RESCHEDULE_APPOINTMENT, arguments))
    gateway.reply(CHAT, json=said("No encuentro esa cita a tu nombre."))
    lucia_writes("Mueve la cita de Marta a las 12")
    tick()
    answer_yes(django_capture_on_commit_callbacks)
    tick()

    theirs.refresh_from_db()
    assert theirs.start == at(MONDAY, "10:00")
    told = json.loads(gateway.sent(CHAT)[1].body["messages"][-1]["content"])
    assert told["error"]["code"] == "appointment.appointment_not_found"
    assert outbound()[-1] == "No encuentro esa cita a tu nombre."


# ── Her cancellation (hub#634; FLOW-F28; WHATSAPP_INBOX-F22): a person's yes, on the card of the number that writes ───


def appointment_answer() -> Flow:
    """The inbox's answer that books appointments, turned on as the owner does it."""
    answer = run("flow.recipe.enable", {"recipe": BOOKING_REF}, ctx_for("hub_owner"))
    return Flow.objects.get(pk=answer.flow.id)


def bea_books(customer_id, *, when: str = "10:00") -> Appointment:
    """Bea's appointment for ``customer_id`` next Monday, far enough ahead of any cancellation notice."""
    bea = make_member("Bea", "Ruiz")
    return make_appointment(Customer.objects.get(pk=customer_id), bea, [make_service("Haircut")], at(next_weekday(0), when))


def refused_after_the_yes(gateway, tick, capture, appointment, arguments: dict, she_writes: str, answer: str) -> str:  # noqa: F811
    """She writes, the assistant wants to cancel with ``arguments`` and the owner says yes: Citas refuses, the appointment
    stays and what the assistant says then goes to her. The code the assistant heard."""
    gateway.reply(CHAT, json=wants(CANCEL_APPOINTMENT, arguments))
    gateway.reply(CHAT, json=said(answer))
    lucia_writes(she_writes)
    tick()
    answer_yes(capture)
    tick()
    appointment.refresh_from_db()
    assert appointment.status == "confirmed"
    assert outbound()[-1] == answer
    return json.loads(gateway.sent(CHAT)[1].body["messages"][-1]["content"])["error"]["code"]


def test_a_customer_cancels_her_appointment_with_any_professional_after_the_owner_s_yes(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    connect()
    appointment_answer()
    door_takes(gateway, 2)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    hers = bea_books(card.id)
    gateway.reply(CHAT, json=wants(CANCEL_APPOINTMENT, {"id": str(hers.id), "reason": "She wrote to cancel"}))
    gateway.reply(CHAT, json=said("Hecho: tu cita del lunes queda anulada."))
    lucia_writes("No puedo ir a mi cita")

    tick()

    hers.refresh_from_db()
    assert hers.status == "confirmed"  # it waits for the yes
    assert outbound() == [DIARY_THANKS]

    answer_yes(django_capture_on_commit_callbacks)
    tick()

    hers.refresh_from_db()
    assert (hers.status, hers.cancelled_by_customer, hers.cancellation_reason) == ("cancelled", True, "She wrote to cancel")
    assert outbound()[-1] == "Hecho: tu cita del lunes queda anulada."
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


def test_the_answer_never_cancels_another_customer_s_appointment_even_after_the_yes(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """WHATSAPP_INBOX-F22: «never someone else's». Whatever the assistant sends, it goes on the card of the number that
    writes, and Citas answers as if that appointment did not exist."""
    connect()
    appointment_answer()
    door_takes(gateway, 2)
    run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    marta = run("customer.customer.create", {"name": "Marta Gil", "phone": "600333444"}, ctx_for("hub_owner"))
    hers = bea_books(marta.id)
    code = refused_after_the_yes(
        gateway,
        tick,
        django_capture_on_commit_callbacks,
        hers,
        {"id": str(hers.id), "customer_id": str(marta.id)},
        "Anula la cita de Marta",
        "No encuentro esa cita a tu nombre.",
    )
    assert code == "appointment.appointment_not_found"


def test_out_of_the_salon_s_policy_the_answer_tells_her_and_the_appointment_stays(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    connect()
    appointment_answer()
    door_takes(gateway, 2)
    make_settings(cancellation_notice_hours=24 * 365)
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"}, ctx_for("hub_owner"))
    hers = bea_books(card.id)
    code = refused_after_the_yes(
        gateway,
        tick,
        django_capture_on_commit_callbacks,
        hers,
        {"id": str(hers.id)},
        "No puedo ir a mi cita",
        "Tu cita ya no se puede anular por aquí.",
    )
    assert code == "appointment.cancellation_notice_required"
