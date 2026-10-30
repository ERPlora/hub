"""«The guest asks for a table by WhatsApp» (WHATSAPP_INBOX-F20, F24, F25), end to end through the worker's real outbox
relay, Automatizaciones' engine and erplora.com's doors.

erplora.com is ``base.tests.fake_gateway`` on 127.0.0.1: its assistant door (``/internal/assistant/chat``) answers
each turn as scripted and its WhatsApp door (``/internal/whatsapp/send``) takes each message, both called by the Hub's
real network code. The inbox's automatic answer is turned on as the owner does it; the guest's message comes in
through the inbox's own door; one tick of the worker hands its event to Automatizaciones, whose run reads the message,
thanks them, makes their card and asks the assistant with only what the answer was granted. «Ask me first»: the booking
it wants waits in «Waiting for your answer»; the owner's yes runs Reservas' real operation, whose answer goes back to
the assistant, and what the assistant says then goes to them. A cancellation too (F25), only of their own reservation:
Reservas refuses any other on their behalf. When the assistant fails, they get the apology and their conversation stays
waiting for an answer, marked «Needs attention».
"""

import datetime as dt
import json
import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

from apps.customer.models import Customer
from apps.flow.models import FlowRun, Question
from apps.flow.queries import TURN
from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.tests.conftest import make_reservation, open_week, set_rules
from apps.whatsapp_inbox.models import Conversation, Message
from apps.whatsapp_inbox.tests.conftest import NOW, connect, ctx_for, receive, run
from base import catalog, worker
from base.catalog import RegisterResult
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

CHAT = "/internal/assistant/chat"
SEND = "/internal/whatsapp/send"
QUOTA = {"used": 1, "limit": 300, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
TABLE_REF = "whatsapp_inbox/reservation_from_whatsapp"
LUCIA = "+34600111222"
THANKS = "Thanks for writing! Let me check the reservations book and I will come straight back to you."
SORRY = (
    "Sorry, I cannot check the reservations right now. Someone from the team will answer you here as soon as they can."
)


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


def test_the_answer_never_cancels_the_reservation_of_another_number(
    gateway, tick, django_capture_on_commit_callbacks  # noqa: F811 - the fixture
):
    """reservations#50: on their behalf, another guest's reservation is refused even after the yes, saying nothing of it;
    the assistant hears the refusal and what it says then goes to them."""
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
    tick()

    theirs.refresh_from_db()
    assert theirs.status != Reservation.Status.CANCELLED
    told = [message for message in gateway.sent(CHAT)[-1].body["messages"] if message.get("role") == "tool"]
    assert "reservation.customer_mismatch" in json.dumps(told)
    assert outbound()[-1] == "No encuentro ninguna reserva a tu nombre."


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
