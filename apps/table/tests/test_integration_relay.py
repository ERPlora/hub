"""Tables with the outbox relay running (``base.relay``, run by the worker on every tick; PLAN-HUB «Eventos entre
módulos», round 2026-10-20): what other apps announce reaches the room through the worker's real loop, on the real
database and the real apps (Reservations, Customers, Sales), without mocks.

- a card erased in Customers (``customer.customer.erased``) leaves the room without her name: her holds forget it
  and the checks she sits at no longer say it (TABLE-F31);
- Reservations holds, moves and releases its tables by calling Tables inside its own transaction (TABLE-F25–F28),
  so a tick that delivers its events afterwards changes nothing: the room stays as the reservation left it, also
  when the party sat long before its time (an old «confirmed» delivered late never holds the table again);
- a check charged in full or voided in Sales frees its table once, however many times the event is delivered
  (TABLE-F18, F20).
"""

import datetime as dt
import threading
from zoneinfo import ZoneInfo

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from live.models import OutboxEvent
from apps.reservation.tests.conftest import book, holds, open_week
from apps.table.live import FLOOR
from apps.table.models import Hold, TableSession
from base import catalog, worker
from base.catalog import RegisterResult

from .conftest import (
    add_line,
    charge,
    make_customer,
    make_table,
    make_zone,
    pin_clock,
    run,
)

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
#: Reservations books from its own «now» (Wednesday 2026-10-14, noon in Madrid): the booking is tomorrow at 21:00.
NOW = dt.datetime(2026, 10, 14, 10, 0, tzinfo=dt.UTC)
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def at(time: str, day: str = "2026-10-15") -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=MADRID)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    pin_clock(monkeypatch, NOW)


@pytest.fixture
def tick(monkeypatch):
    """``tick()``: one turn of the worker's real loop (relay included), without the SaaS (``register_apps``) and,
    inside a test's transaction, without releasing the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def turn() -> None:
        stop = threading.Event()

        def wait(seconds: float) -> bool:
            stop.set()
            return True

        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: NOW) == 0

    return turn


@pytest.fixture
def terrace(db):
    open_week()
    return make_table("5", zone=make_zone("Terrace"), capacity=4)


def snapshot(reservation_id) -> list[tuple]:
    return [
        (h.table_id, h.status, h.held_from, h.held_until, h.party_size, h.label, h.customer_id)
        for h in holds(reservation_id)
    ]


def plan_status(table) -> str:
    return run("table.table.get", {"id": str(table.id)}).status


# ── Customers: an erased card (TABLE-F31) ────────────────────────────────────────────────────────


def test_an_erased_customer_is_forgotten_in_the_rooms_holds_and_checks_by_the_relay(terrace, tick, monkeypatch):
    ana = make_customer("Ana García", phone="600111222")
    out = book(table_id=str(terrace.id), customer_id=str(ana.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    bar = make_table("2", zone=make_zone("Bar"))
    seated = run(
        "table.session.open",
        {"table_id": str(bar.id), "guests_count": 2, "customer_id": str(ana.id)},
    )
    tick()
    [hold] = holds(out.id)
    assert (hold.label, hold.customer_id) == ("Ana García", ana.id)

    run("customer.customer.erase", {"id": str(ana.id), "reason": "She asked for it"})
    [hold] = holds(out.id)
    assert hold.label == "Ana García"  # the erasure reaches the room through the relay, not inline
    tick()

    [hold] = holds(out.id)
    assert (hold.status, hold.label, hold.customer_id) == ("held", "", ana.id)
    # That evening the plan still sets the table aside at its hour, without her name.
    pin_clock(monkeypatch, at("20:30"))
    floor = run("table.table.get", {"id": str(terrace.id)})
    assert (floor.status, floor.hold.label, floor.hold.erased) == ("reserved", "", True)
    [check] = run("table.table.get", {"id": str(bar.id)}).checks
    assert (check.id, check.customer_id, check.customer_name) == (seated.id, None, None)


def test_a_hold_that_forgets_a_name_says_so_and_the_live_plan_paints_it_again(terrace, tick):
    # The plan is live (TABLE-F09): the reaction's change of a hold re-runs it, as any other change of a hold.
    ana = make_customer("Ana García", phone="600111222")
    out = book(table_id=str(terrace.id), customer_id=str(ana.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    tick()
    run("customer.customer.erase", {"id": str(ana.id), "reason": "She asked for it"})
    seen = set(OutboxEvent.objects.values_list("id", flat=True))
    tick()
    told = [
        (event.name, event.payload)
        for event in OutboxEvent.objects.exclude(id__in=seen).filter(name__startswith="table.")
    ]
    assert told == [
        (
            "table.table.held",
            {"table_id": str(terrace.id), "source": "reservation", "source_ref": str(out.id)},
        )
    ]
    assert "table.table.held" in FLOOR


def test_erasing_the_card_a_duplicate_was_merged_into_forgets_the_duplicates_holds_too(terrace, tick):
    # tables#127: the hold keeps the absorbed card's id; erasing the card that stays erases the absorbed one too.
    absorbed = make_customer("Ana G.", phone="600111333")
    survivor = make_customer("Ana García", phone="600111222")
    out = book(table_id=str(terrace.id), customer_id=str(absorbed.id), guest_name="Ana G.")
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("customer.customer.merge", {"id": str(survivor.id), "absorbed_id": str(absorbed.id)})
    tick()
    [hold] = holds(out.id)
    assert (hold.label, hold.customer_id) == ("Ana G.", absorbed.id)
    run("customer.customer.erase", {"id": str(survivor.id), "reason": "She asked for it"})
    tick()
    [hold] = holds(out.id)
    assert (hold.status, hold.label) == ("held", "")


# ── Reservations: the call inside its transaction is the one that counts (TABLE-F25–F28) ────────


def test_a_confirmed_reservations_events_delivered_later_keep_its_one_hold_as_it_was(terrace, tick):
    out = book(table_id=str(terrace.id), party_size=4)
    run("reservation.reservation.confirm", {"id": str(out.id)})
    before = snapshot(out.id)
    assert [row[1] for row in before] == ["held"]
    tick()
    assert snapshot(out.id) == before
    assert Hold.objects.count() == 1


def test_a_moved_reservation_ends_where_it_was_last_moved_after_the_relay(terrace, tick):
    bar = make_table("2", zone=make_zone("Bar"))
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("reservation.reservation.update", {"id": str(out.id), "time": "21:30", "party_size": 3})
    run("reservation.reservation.update", {"id": str(out.id), "table": "2", "zone": "Bar"})
    tick()
    [hold] = holds(out.id)
    assert (hold.table_id, hold.status, hold.held_from, hold.party_size) == (bar.id, "held", at("21:30"), 3)

    run("reservation.reservation.update", {"id": str(out.id), "no_table": True})
    tick()
    [hold] = holds(out.id)
    assert (hold.status, hold.label) == ("released", "")


@pytest.mark.parametrize("action", ["cancel", "no_show", "delete"])
def test_a_cancelled_no_show_or_deleted_reservation_stays_released_after_the_relay(terrace, tick, action):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run(f"reservation.reservation.{action}", {"id": str(out.id)})
    tick()
    [hold] = holds(out.id)
    assert (hold.status, hold.label) == ("released", "")


def test_a_party_seated_long_before_its_time_is_not_held_again_by_a_late_confirmation(terrace, tick):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("reservation.reservation.seat", {"id": str(out.id)})
    assert [hold.status for hold in holds(out.id)] == ["released"]
    tick()
    assert [hold.status for hold in holds(out.id)] == ["released"]
    assert TableSession.objects.filter(table=terrace, status="open").count() == 1


def test_a_party_seated_at_its_time_keeps_its_hold_spent_after_the_relay(terrace, tick, monkeypatch):
    out = book(table_id=str(terrace.id), party_size=3)
    run("reservation.reservation.confirm", {"id": str(out.id)})
    pin_clock(monkeypatch, at("20:55"))
    run("reservation.reservation.seat", {"id": str(out.id)})
    tick()
    assert [(hold.status, hold.label) for hold in holds(out.id)] == [("consumed", "")]
    assert plan_status(terrace) == "occupied"


# ── Sales: a check charged or voided (TABLE-F18, F20) ────────────────────────────────────────────


@pytest.mark.parametrize("ending", ["charged", "voided"])
def test_a_check_charged_or_voided_in_sales_frees_its_table_once_after_the_relay(terrace, tick, product, ending):
    seated = run("table.session.open", {"table_id": str(terrace.id), "guests_count": 2})
    coffee = product()
    add_line(seated.order_id, coffee)
    if ending == "charged":
        charge(seated.order_id, key="relay")
    else:
        run("sale.order.void", {"order_id": str(seated.order_id)})
    tick()
    session = TableSession.objects.get(pk=seated.id)
    assert (session.status, plan_status(terrace)) == ("closed", "available")
    closed_at = session.closed_at
    tick()
    session.refresh_from_db()
    assert session.closed_at == closed_at
