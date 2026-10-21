"""The table app's events and its reactions to Sales', Customers' and Reservations' events.

Cases from the old module's tests: session_history.hub (charging the check in full frees the table; a
partial charge does not), customer_erasure.postgres (the floor forgets an erased customer's name, a
finished hold keeps no name), reservation_handoff.postgres (a reservation's status drives its hold, its
update moves it). Each reaction runs as the system through an operation of this app; delivering it twice
changes nothing.
"""

import datetime as dt
import uuid
from pathlib import Path

import pytest
from django.utils import timezone
from live.context import system_context

from apps.table import events
from apps.table.models import Hold, TableSession

from .conftest import A, make_hold, make_session, make_table, make_zone, open_check, run

pytestmark = pytest.mark.django_db

EVENTS_SOURCE = Path(events.__file__).read_text()


def test_every_event_is_named_app_entity_fact():
    assert events.ALL == [
        "table.zone.created",
        "table.zone.updated",
        "table.zone.deleted",
        "table.table.created",
        "table.table.updated",
        "table.table.deleted",
        "table.table.held",
        "table.table.hold_released",
        "table.session.opened",
        "table.session.closed",
        "table.session.transferred",
        "table.session.merged",
        "table.session.split",
        "table.session.updated",
        "table.session.parked",
        "table.session.restored",
        "table.session.deleted",
        "table.settings.updated",
    ]


def test_the_reactions_are_the_workbooks():
    assert events.REACTIONS == {
        "sale.order.completed": "table.session.close_by_order",
        "sale.order.voided": "table.session.close_by_order",
        "customer.customer.erased": "table.hold.forget_customer",
    }


@pytest.mark.parametrize(
    "fact", ["reservation.reservation.status_changed", "reservation.reservation.updated"]
)
def test_a_reservations_event_is_no_reaction_its_call_inside_reservations_is(fact):
    """Reservations holds, moves and releases its table by calling Tables in its own transaction (TABLE-F25–F27):
    the same event delivered later by the relay would apply a stale reservation (test_integration_relay.py)."""
    table = make_table("6", zone=make_zone())
    assert events.react(A, fact, reservation("confirmed", table)) is None
    assert Hold.objects.count() == 0


def test_an_event_without_a_reaction_does_nothing():
    assert (
        events.react(A, "sale.sale.completed", {"sale_id": str(uuid.uuid7())}) is None
    )


# ── Sales ────────────────────────────────────────────────────────────────────────────────────────


def test_a_check_charged_in_full_closes_its_table_checks_once():
    table = make_table("4", zone=make_zone())
    order = open_check("Table 4")
    session = make_session(table, order_id=order.id)
    other = make_session(make_table("5"), order_id=open_check("Table 5").id)
    assert (
        events.react(A, "sale.order.completed", {"order_id": str(order.id)}).closed == 1
    )
    session.refresh_from_db()
    other.refresh_from_db()
    assert (session.status, other.status) == ("closed", "open")
    assert session.closed_at is not None
    assert session.moves.get().release_reason == "closed"
    # Delivered again: nothing left to close.
    assert (
        events.react(A, "sale.order.completed", {"order_id": str(order.id)}).closed == 0
    )


def test_a_check_voided_in_sales_frees_its_table():
    # TABLE-F20: eliminating the table's check in Sales frees the table (the old module never heard it).
    order = open_check("Table 4")
    session = make_session(make_table("4"), order_id=order.id)
    events.react(A, "sale.order.voided", {"order_id": str(order.id)})
    session.refresh_from_db()
    assert session.status == "closed"


@pytest.mark.parametrize("fact", ["sale.order.completed", "sale.order.voided"])
def test_a_parked_check_charged_or_voided_in_sales_closes_too(fact):
    # A parked check is still an open account: once Sales ends it, it is over (never «Parked» forever).
    order = open_check("Ana")
    parked = TableSession.objects.create(table=None, status="parked", order_id=order.id)
    assert events.react(A, fact, {"order_id": str(order.id)}).closed == 1
    parked.refresh_from_db()
    assert (parked.status, parked.table_id, parked.closed_at is not None) == ("closed", None, True)


# ── Customers ────────────────────────────────────────────────────────────────────────────────────


def test_an_erased_customer_leaves_every_hold_of_hers_without_her_name():
    table = make_table("8", zone=make_zone())
    ana, luis = uuid.uuid7(), uuid.uuid7()
    live = make_hold(table, ref="r-1", label="Ana", customer_id=ana)
    done = make_hold(table, ref="r-2", label="Ana", customer_id=ana, status="consumed")
    other = make_hold(table, ref="r-3", label="Luis", customer_id=luis)
    events.react(A, "customer.customer.erased", {"id": str(ana)})
    for hold in (live, done, other):
        hold.refresh_from_db()
    assert (live.label, done.label, other.label) == ("", "", "Luis")
    # The hold stays: the table is still set aside at its hour.
    assert (live.status, live.customer_id) == ("held", ana)


def test_an_erasure_without_a_card_touches_no_hold():
    hold = make_hold(make_table("8"), ref="walk-in", label="Pedro")
    events.react(A, "customer.customer.erased", {"id": None})
    hold.refresh_from_db()
    assert hold.label == "Pedro"


# ── Reservations: the operations it calls by name inside its transaction ─────────────────────────


def reservation(status: str, table, ref: str = "res-1", **more) -> dict:
    start = timezone.localtime() + dt.timedelta(minutes=30)
    return {
        "id": ref,
        "status": status,
        "table_id": str(table.id) if table else None,
        "date": start.date().isoformat(),
        "time": start.strftime("%H:%M"),
        "duration_minutes": 90,
        "party_size": 4,
        "guest_name": "Ana",
        "customer_id": str(uuid.uuid7()),
        **more,
    }


def sync(payload: dict):
    return run("table.hold.sync_reservation", payload, system_context(A))


def move(payload: dict):
    return run("table.hold.move_reservation", payload, system_context(A))


def test_a_confirmed_reservation_holds_its_table_once_in_the_business_zone():
    table = make_table("6", zone=make_zone())
    payload = reservation("confirmed", table)
    sync(payload)
    sync(payload)
    hold = Hold.objects.get()
    assert (hold.source, hold.source_ref, hold.status, hold.label, hold.party_size) == (
        "reservation",
        "res-1",
        "held",
        "Ana",
        4,
    )
    local = timezone.localtime(hold.held_from)
    assert local.strftime("%H:%M") == payload["time"]
    assert hold.held_until - hold.held_from == dt.timedelta(minutes=90)


def test_a_cancelled_or_no_show_reservation_releases_its_hold_without_its_name():
    table = make_table("6", zone=make_zone())
    sync(reservation("confirmed", table)
    )
    sync(reservation("cancelled", table)
    )
    hold = Hold.objects.get()
    assert (hold.status, hold.label) == ("released", "")
    # A hold already consumed (the party sat down) is not touched.
    sync(
        reservation("confirmed", table, "res-2"),
    )
    Hold.objects.filter(source_ref="res-2").update(status="consumed")
    sync(
        reservation("no_show", table, "res-2"),
    )
    assert Hold.objects.get(source_ref="res-2").status == "consumed"


def test_a_reservation_on_a_deleted_or_inactive_table_holds_nothing():
    gone = make_table("1", is_deleted=True, deleted_at=timezone.now())
    idle = make_table("2", is_active=False)
    for table in (gone, idle):
        sync(
            reservation("confirmed", table, f"r-{table.number}"),
        )
    assert Hold.objects.count() == 0


def test_an_updated_reservation_moves_its_hold_and_one_without_a_table_releases_it():
    zone = make_zone()
    old, new = make_table("1", zone=zone), make_table("2", zone=zone)
    sync(reservation("confirmed", old)
    )
    later = timezone.localtime() + dt.timedelta(hours=2)
    move(
        {
            "id": "res-1",
            "table_id": str(new.id),
            "time": later.strftime("%H:%M"),
            "date": later.date().isoformat(),
        },
    )
    hold = Hold.objects.get()
    assert (hold.table_id, timezone.localtime(hold.held_from).strftime("%H:%M")) == (
        new.id,
        later.strftime("%H:%M"),
    )
    move({"id": "res-1", "table_id": None}
    )
    hold.refresh_from_db()
    assert (hold.status, hold.label) == ("released", "")


def test_every_own_event_is_a_literal_of_events_py():
    for name in events.ALL:
        assert f'"{name}"' in EVENTS_SOURCE, name
