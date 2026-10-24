"""«The customer gets the notice when the salon confirms» (WHATSAPP_INBOX-F23, FLOW-F31) and its table companion
«… when the restaurant confirms» (WHATSAPP_INBOX-F26, RESERVATION-F19), end to end through the worker's real outbox
relay (``base/relay.py``; ``apps/task/tests/test_relay.py`` is the pattern).

The inbox's factory automation is turned on as the owner does it; Citas' real operation confirms the appointment and
records its event; one tick of the worker's real loop hands it to Automatizaciones, whose run reads the card, finds
the conversation of exactly that number, reads the appointment and sends through ``whatsapp_inbox.message.notify``:
the message is in the conversation and erplora.com's door 5 (``respx``, Meta beyond it) was called once. A second
tick sends nothing; another business sends through its own number; without a conversation of exactly that number,
or with the month spent, nothing leaves and the reason is in the automation's history.

The table's notice runs on Reservas' and Customers' real operations: a reservation confirmed by the staff, or born
confirmed when the book confirms by itself, tells the guest once in the conversation of exactly the reservation's
number; any other change of status (cancelled, no-show…) tells nobody.
"""

import datetime as dt
import json
import threading

import httpx
import pytest
import respx
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import get

from apps.appointment.tests.conftest import MONDAY, at, make_appointment, make_member, make_service
from apps.appointment.tests.conftest import ctx_for as appointment_ctx
from apps.customer.models import Customer
from apps.reservation.tests.conftest import make_reservation, open_week, set_rules
from apps.flow.models import FlowRun
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import B, NOW, card, connect, ctx_for, receive, run, system, template
from base import catalog, worker
from base.catalog import RegisterResult

pytestmark = pytest.mark.django_db

SEND = "http://saas.test/internal/whatsapp/send"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
REF = "whatsapp_inbox/appointment_confirmed"
ANA = "+34600111222"
#: The approved Utility template the recipe goes with after the customer's 24 hours.
CONFIRMED = template("appointment_confirmed", variables=4, body="Confirmada: {{1}} a las {{2}}, {{3}} con {{4}}.")
RESERVATION_REF = "whatsapp_inbox/reservation_confirmed"
#: The table's Utility template: the day, the time and the guests.
TABLE_CONFIRMED = template("reservation_confirmed", variables=3, body="Confirmada: {{1}} a las {{2}}, mesa para {{3}}.")
#: The day after ``NOW`` (Thursday 15 October 2026), the reservation's day.
FRIDAY = (NOW + dt.timedelta(days=1)).date()


@pytest.fixture
def tick(monkeypatch, django_capture_on_commit_callbacks):
    """One turn of the worker's real loop, without the SaaS's catalogue and, inside the test's transaction,
    without releasing its connection; what the run leaves for after its COMMIT (the delivery) runs too."""
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


@pytest.fixture
def door():
    with respx.mock(assert_all_called=False) as mock:
        yield mock.post(SEND).mock(return_value=httpx.Response(200, json={"wa_message_id": "wamid.OUT"}))


def salon(phone: str = "600111222", *, minutes_ago: int = 10, templates=(CONFIRMED,), **channel):
    """The owner's business: its number connected, Lucía's conversation (her last message ``minutes_ago``), her card
    made by Customers, a pending appointment of hers with Ana and the inbox's automation turned on."""
    connect(templates=list(templates), **channel)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=minutes_ago)).isoformat())
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": phone}, ctx_for("hub_owner"))
    run("flow.recipe.enable", {"recipe": REF}, ctx_for("hub_owner"))
    cut = make_service("Haircut", price=2000, duration=30)
    ana = make_member("Ana", "López")
    return make_appointment(Customer.objects.get(pk=card.id), ana, [cut], at(MONDAY, "10:00"), status="pending")


def confirm(appointment, scope=None) -> None:
    op = get("appointment.appointment.confirm")
    ctx = appointment_ctx("hub_admin", **({"scope": scope} if scope else {}))
    op(ctx, op.input.model_validate({"id": str(appointment.id)}))


def outbound() -> list[Message]:
    return list(Message.objects.filter(direction="outbound").select_related("conversation").order_by("created_at"))


def test_confirming_tells_the_customer_once_in_her_conversation_through_erplora(tick, door):
    appointment = salon()
    confirm(appointment)
    assert OutboxEvent.objects.filter(name="appointment.appointment.confirmed").count() == 1
    assert not outbound()  # nothing is sent inside the request that confirmed

    tick()

    run_row = FlowRun.objects.get()
    assert (run_row.event_name, run_row.status) == ("appointment.appointment.confirmed", "succeeded")
    [message] = outbound()
    assert (message.conversation.phone, message.kind, message.status, message.host) == (ANA, "text", "sent", "a")
    assert message.body.startswith("Confirmed! We are expecting you on Monday, ")
    assert message.body.endswith(" at 10:00 for your Haircut with Ana López.")
    assert [json.loads(call.request.content)["to"] for call in door.calls] == [ANA]
    assert OutboxEvent.objects.filter(name="whatsapp_inbox.message.sent").count() == 1

    tick()
    assert (FlowRun.objects.count(), len(outbound()), door.call_count) == (1, 1, 1)


def test_after_the_24_hours_it_goes_with_the_approved_utility_template(tick, door):
    confirm(salon(minutes_ago=3 * 24 * 60))
    tick()
    [message] = outbound()
    assert (message.kind, message.template_name) == ("template", "appointment_confirmed")
    sent = json.loads(door.calls.last.request.content)["template"]
    assert sent["name"] == "appointment_confirmed"
    assert sent["variables"][1:] == ["10:00", "Haircut", "Ana López"]


def test_without_a_conversation_of_exactly_that_number_nothing_leaves_and_the_history_says_why(tick, door):
    confirm(salon(phone="600111223"))  # Lucía's card has a number that never wrote: not Ana's conversation
    tick()
    run_row = FlowRun.objects.get()
    assert run_row.status == "stopped"
    assert [entry["step"] for entry in run_row.log if entry["outcome"] == "stopped"] == ["s4"]
    assert not outbound() and door.call_count == 0


def test_with_the_month_spent_nothing_leaves_and_the_history_says_why(tick, door):
    confirm(salon(monthly_limit=150, monthly_usage=150))
    tick()
    run_row = FlowRun.objects.get()
    assert (run_row.status, run_row.error_code) == ("failed", "whatsapp_inbox.cap_reached")
    assert not outbound() and door.call_count == 0


def test_another_business_tells_its_customer_through_its_own_number(tick, door):
    appointment = salon()
    system(
        "whatsapp_inbox.channel.sync",
        # A plan with messages: since hub#158 a limit of 0 means the plan includes none, not «no cap».
        {"version": 1, "status": "connected", "phone_number": "+34910000001", "monthly_limit": 150, "monthly_usage": 0, "templates": [CONFIRMED]},
        B,
    )
    confirm(appointment, scope=B)
    tick()
    [message] = outbound()
    assert message.host == "b"
    assert json.loads(door.calls.last.request.content)["hub"] == "b"
    sent = OutboxEvent.objects.get(name="whatsapp_inbox.message.sent")
    assert (sent.scope_kind, sent.scope_key) == (B.kind, B.key)


# ── WHATSAPP_INBOX-F26 / RESERVATION-F19: the restaurant confirms the table ─────────────────────────────


@pytest.fixture
def restaurant_clock(monkeypatch):
    """Reservas books against Django's clock: it reads ``NOW`` too, so «tomorrow» is Friday 16 October."""
    monkeypatch.setattr("django.utils.timezone.now", lambda: NOW)


def restaurant(
    *, minutes_ago: int = 10, templates=(TABLE_CONFIRMED,), auto_confirm: bool = False, language: str = "en", **channel
):
    """The owner's restaurant: its number connected, Lucía's conversation (her last message ``minutes_ago``), its
    lunch and dinner every day, «Las reservas se confirman solas» as given and the inbox's table notice turned on by
    the owner in ``language``."""
    connect(templates=list(templates), **channel)
    receive("wamid.IN", sent_at=(NOW - dt.timedelta(minutes=minutes_ago)).isoformat())
    open_week()
    set_rules(auto_confirm=auto_confirm)
    run("flow.recipe.enable", {"recipe": RESERVATION_REF}, ctx_for("hub_owner", language=language))


def book(phone: str = "600111222", **data):
    """Reservas' real booking for Friday at 21:00, four guests: the phone finds or makes the card (Customers)."""
    payload = {"guest_name": "Lucía Pérez", "guest_phone": phone, "date": FRIDAY.isoformat(), "time": "21:00",
               "party_size": 4, **data}
    return run("reservation.reservation.create", payload, ctx_for("hub_admin"))


def act(name: str, reservation_id, scope=None, **data) -> None:
    """A change of Reservas made by the staff (``reservation.reservation.confirm``, ``cancel``…)."""
    ctx = ctx_for("hub_admin", **({"scope": scope} if scope else {}))
    run(name, {"id": str(reservation_id), **data}, ctx)


def table_runs() -> list[FlowRun]:
    return list(FlowRun.objects.filter(event_name="reservation.reservation.status_changed").order_by("started_at"))


def test_confirming_a_reservation_tells_the_guest_once_in_her_conversation(restaurant_clock, tick, door):
    restaurant()
    reservation = book()
    assert reservation.status == "pending"
    tick()
    assert not table_runs() and not outbound()  # booked pending: nothing to tell yet

    act("reservation.reservation.confirm", reservation.id)
    assert not outbound()  # nothing is sent inside the request that confirmed
    tick()

    [run_row] = table_runs()
    assert run_row.status == "succeeded"
    [message] = outbound()
    assert (message.conversation.phone, message.kind, message.status, message.host) == (ANA, "text", "sent", "a")
    assert message.body == "Confirmed! We are expecting you on Friday, Oct. 16, 2026 at 21:00, table for 4."
    assert [json.loads(call.request.content)["to"] for call in door.calls] == [ANA]

    tick()
    assert (len(table_runs()), len(outbound()), door.call_count) == (1, 1, 1)


def test_in_spanish_it_says_the_day_in_the_business_s_language(restaurant_clock, tick, door):
    restaurant(language="es")
    act("reservation.reservation.confirm", book().id)
    tick()
    [message] = outbound()
    assert message.body == "¡Confirmada! Te esperamos el viernes, 16 de octubre de 2026 a las 21:00, mesa para 4."


def test_a_reservation_born_confirmed_tells_the_guest_too(restaurant_clock, tick, door):
    restaurant(auto_confirm=True)
    reservation = book()
    assert reservation.status == "confirmed"
    tick()
    [run_row] = table_runs()
    assert run_row.status == "succeeded"
    [message] = outbound()
    assert message.conversation.phone == ANA
    assert message.body.endswith("at 21:00, table for 4.")


def test_any_other_change_of_status_tells_nobody(restaurant_clock, tick, door):
    restaurant()
    reservation = book()
    act("reservation.reservation.confirm", reservation.id)
    tick()
    assert len(outbound()) == 1

    act("reservation.reservation.cancel", reservation.id)
    other = book(time="13:30")
    act("reservation.reservation.confirm", other.id)
    act("reservation.reservation.no_show", other.id)
    tick()
    # Cancelled and no-show start nothing: only the two confirmations ran and told her.
    assert (len(table_runs()), len(outbound()), door.call_count) == (2, 2, 2)


def test_after_the_24_hours_the_table_notice_goes_with_its_utility_template(restaurant_clock, tick, door):
    restaurant(minutes_ago=3 * 24 * 60)
    act("reservation.reservation.confirm", book().id)
    tick()
    [message] = outbound()
    assert (message.kind, message.template_name) == ("template", "reservation_confirmed")
    sent = json.loads(door.calls.last.request.content)["template"]
    assert sent["name"] == "reservation_confirmed"
    assert sent["variables"] == ["Friday, Oct. 16, 2026", "21:00", "4"]


def test_without_a_conversation_of_exactly_the_reservation_s_number_nothing_leaves(restaurant_clock, tick, door):
    restaurant()
    act("reservation.reservation.confirm", book(phone="600111223").id)  # a number that never wrote
    tick()
    [run_row] = table_runs()
    assert run_row.status == "stopped"
    assert [entry["step"] for entry in run_row.log if entry["outcome"] == "stopped"] == ["s4"]
    assert not outbound() and door.call_count == 0


def test_a_number_that_is_not_international_tells_nobody(restaurant_clock, tick, door):
    restaurant()
    lucia = card("Lucía Pérez", "600111222")  # her card says +34600111222, the reservation keeps what was typed
    act("reservation.reservation.confirm", book(customer_id=str(lucia.id)).id)
    tick()
    [run_row] = table_runs()
    assert run_row.status == "stopped"
    assert [entry["step"] for entry in run_row.log if entry["outcome"] == "stopped"] == ["s4"]
    assert not outbound() and door.call_count == 0


def test_without_a_phone_on_the_reservation_it_stops_before_it_looks(restaurant_clock, tick, door):
    restaurant()
    reservation = make_reservation(FRIDAY, "21:00", status="pending", guest_phone="")
    act("reservation.reservation.confirm", reservation.id)
    tick()
    [run_row] = table_runs()
    assert run_row.status == "stopped"
    assert [entry["step"] for entry in run_row.log if entry["outcome"] == "stopped"] == ["s2"]
    assert not outbound() and door.call_count == 0


def test_another_restaurant_tells_its_guest_through_its_own_number(restaurant_clock, tick, door):
    restaurant()
    reservation = book()
    system(
        "whatsapp_inbox.channel.sync",
        {"version": 1, "status": "connected", "phone_number": "+34910000001", "monthly_limit": 150,
         "monthly_usage": 0, "templates": [TABLE_CONFIRMED]},
        B,
    )
    act("reservation.reservation.confirm", reservation.id, scope=B)
    tick()
    [message] = outbound()
    assert message.host == "b"
    assert json.loads(door.calls.last.request.content)["hub"] == "b"
    sent = OutboxEvent.objects.get(name="whatsapp_inbox.message.sent")
    assert (sent.scope_kind, sent.scope_key) == (B.kind, B.key)
