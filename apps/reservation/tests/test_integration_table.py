"""Reservations with the real Tables app (TABLE-F25–F28, «Contrato con Reservas»): a confirmed reservation
holds its table, a change moves the hold, cancelling releases it, and seating seats the table and opens its
check in Sales. Nothing is mocked: the holds, the checks and the floor plan are Tables' and Sales' own.
"""

import datetime as dt

import pytest

from apps.customer.models import OrderLink
from apps.reservation.models import Reservation
from apps.sale.models import Order
from apps.table.models import Hold, TableSession

from .conftest import (
    MADRID,
    THURSDAY,
    book,
    ctx_for,
    holds,
    make_slot,
    make_table,
    make_zone,
    open_week,
    pin_clock,
    run,
    set_rules,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture(autouse=True)
def week(db):
    open_week()


@pytest.fixture
def terrace(db):
    return make_table("5", zone=make_zone("Terrace"), capacity=4)


def at(day: str, time: str) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=MADRID)


def plan_status(table) -> str:
    return run("table.table.get", {"id": str(table.id)}, ctx_for(EMPLOYEE)).status


def test_a_pending_reservation_holds_nothing_and_confirming_it_holds_its_table(terrace):
    out = book(table_id=str(terrace.id), party_size=4)
    assert holds(out.id) == []
    run("reservation.reservation.confirm", {"id": str(out.id)}, ctx_for(EMPLOYEE))
    [hold] = holds(out.id)
    assert (hold.table_id, hold.status, hold.party_size, hold.label) == (
        terrace.id,
        "held",
        4,
        "Ana García",
    )
    assert (hold.held_from, hold.held_until) == (
        at("2026-10-15", "21:00"),
        at("2026-10-15", "23:00"),
    )
    assert hold.customer_id == Reservation.objects.get(pk=out.id).customer_id


def test_a_reservation_born_confirmed_holds_its_table(terrace):
    set_rules(auto_confirm=True)
    out = book(table="5", zone="Terrace")
    assert [hold.status for hold in holds(out.id)] == ["held"]


def test_the_plan_shows_the_table_reserved_only_from_an_hour_before(
    terrace, monkeypatch
):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    assert plan_status(terrace) == "available"
    pin_clock(monkeypatch, at("2026-10-15", "20:05"))
    assert plan_status(terrace) == "reserved"


def test_changing_a_confirmed_reservation_moves_its_hold(terrace):
    bar = make_table("2", zone=make_zone("Bar"))
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run(
        "reservation.reservation.update",
        {"id": str(out.id), "time": "21:30", "party_size": 3},
    )
    [hold] = holds(out.id)
    assert (hold.held_from, hold.party_size, hold.table_id) == (
        at("2026-10-15", "21:30"),
        3,
        terrace.id,
    )
    run(
        "reservation.reservation.update",
        {"id": str(out.id), "table": "2", "zone": "Bar"},
    )
    [hold] = holds(out.id)
    assert (hold.table_id, hold.status) == (bar.id, "held")
    run("reservation.reservation.update", {"id": str(out.id), "no_table": True})
    [hold] = holds(out.id)
    assert hold.status == "released"
    assert Reservation.objects.get(pk=out.id).table_id is None


def test_giving_a_table_to_a_confirmed_reservation_holds_it(terrace):
    out = book()
    run("reservation.reservation.confirm", {"id": str(out.id)})
    assert holds(out.id) == []
    run(
        "reservation.reservation.update",
        {"id": str(out.id), "table_id": str(terrace.id)},
    )
    assert [hold.status for hold in holds(out.id)] == ["held"]


@pytest.mark.parametrize("action", ["cancel", "no_show", "delete"])
def test_cancelling_a_no_show_or_deleting_releases_the_table(terrace, action):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run(f"reservation.reservation.{action}", {"id": str(out.id)})
    [hold] = holds(out.id)
    assert (hold.status, hold.label) == ("released", "")


def test_seating_seats_the_table_and_opens_its_check_with_the_customer(
    terrace, monkeypatch
):
    out = book(table_id=str(terrace.id), party_size=3)
    run("reservation.reservation.confirm", {"id": str(out.id)})
    pin_clock(monkeypatch, at("2026-10-15", "20:55"))
    seated = run("reservation.reservation.seat", {"id": str(out.id)}, ctx_for(EMPLOYEE))
    session = TableSession.objects.get(table=terrace, status="open")
    assert (seated.status, seated.table_session_id) == ("seated", session.id)
    assert session.guests_count == 3
    assert Order.objects.get(pk=session.order_id).status == "open"
    assert (
        OrderLink.objects.get(order_id=session.order_id).customer_id
        == seated.customer_id
    )
    assert [hold.status for hold in holds(out.id)] == ["consumed"]
    assert plan_status(terrace) == "occupied"


def test_a_party_seated_long_before_its_time_does_not_leave_the_table_reserved_later(
    terrace,
):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("reservation.reservation.seat", {"id": str(out.id)})
    assert TableSession.objects.filter(table=terrace, status="open").count() == 1
    assert [hold.status for hold in holds(out.id)] == ["released"]


def test_seating_at_a_table_taken_by_somebody_else_is_refused_and_changes_nothing(
    terrace, monkeypatch
):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("table.session.open", {"table_id": str(terrace.id), "guests_count": 2})
    from live.errors import Conflict

    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.seat", {"id": str(out.id)})
    assert caught.value.code == "reservation.table_not_free"
    assert caught.value.message == (
        "Table 5 (Terrace) is taken right now: free it, or move the reservation to another table before seating it."
    )
    assert Reservation.objects.get(pk=out.id).status == "confirmed"
    assert TableSession.objects.filter(table=terrace, status="open").count() == 1


def test_a_party_seated_from_the_floor_plan_is_marked_seated_on_its_table(
    terrace, monkeypatch
):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    pin_clock(monkeypatch, at("2026-10-15", "20:50"))
    opened = run("table.session.open", {"table_id": str(terrace.id)})
    assert opened.guests_count == 4
    assert [hold.status for hold in holds(out.id)] == ["consumed"]
    seated = run("reservation.reservation.seat", {"id": str(out.id)})
    assert (seated.status, seated.table_session_id) == ("seated", opened.id)
    assert TableSession.objects.filter(table=terrace, status="open").count() == 1


def test_seating_without_a_table_only_marks_the_reservation():
    out = book()
    seated = run("reservation.reservation.seat", {"id": str(out.id)})
    assert (seated.status, seated.table_session_id) == ("seated", None)
    assert TableSession.objects.count() == 0


def test_a_refused_change_leaves_the_hold_where_it_was(terrace):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    from live.errors import Conflict

    with pytest.raises(Conflict):
        run("reservation.reservation.update", {"id": str(out.id), "time": "18:00"})
    [hold] = holds(out.id)
    assert hold.held_from == at("2026-10-15", "21:00")


def test_the_reservation_reads_its_tables_label_as_tables_writes_it(terrace):
    out = book(table_id=str(terrace.id))
    run("table.table.update", {"id": str(terrace.id), "number": "15"})
    assert (
        run("reservation.reservation.get", {"id": str(out.id)}).table_label
        == "15 (Terrace)"
    )


def test_the_free_tables_follow_what_tables_and_reservations_say(terrace):
    other = make_table("6", zone=terrace.zone, capacity=2)
    book(table_id=str(terrace.id))
    free = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:30", "party_size": 2},
        ctx_for(EMPLOYEE),
    )
    assert [(row.number, row.free) for row in free.rows] == [("6", True), ("5", False)]
    run("table.table.update", {"id": str(other.id), "blocked": True})
    free = run(
        "reservation.availability.tables", {"date": "2026-10-15", "time": "21:30"}
    )
    assert [row.number for row in free.rows] == ["5"]


def test_a_hold_for_a_reservation_with_a_slot_of_another_day(terrace):
    make_slot(THURSDAY + 1, "00:00", "03:00")
    out = book(table_id=str(terrace.id), date="2026-10-16", time="00:30")
    run("reservation.reservation.confirm", {"id": str(out.id)})
    [hold] = holds(out.id)
    assert hold.held_from == at("2026-10-16", "00:30")
    assert Hold.objects.filter(table=terrace, status="held").count() == 1


# ── Review of 2026-10-15 ─────────────────────────────────────────────────────────────────────────


def test_a_reservation_whose_hold_another_party_spent_is_refused_not_hung_on_its_check(terrace, monkeypatch):
    # Tables spends every hold of the table inside the hour before when a party sits (TABLE-F28): seating A
    # at 20:10 spends B's hold of 21:00 too. B arriving at 21:05 with A still at the table must be told the
    # table is taken, never hung on A's check.
    make_slot(THURSDAY, "17:00", "20:00")
    first = book(table_id=str(terrace.id), time="19:00", guest_name="Ana", guest_phone="600111222")
    second = book(table_id=str(terrace.id), time="21:00", guest_name="Bea", guest_phone="600333444")
    for reservation in (first, second):
        run("reservation.reservation.confirm", {"id": str(reservation.id)})
    pin_clock(monkeypatch, at("2026-10-15", "20:10"))
    seated = run("reservation.reservation.seat", {"id": str(first.id)})
    assert [hold.status for hold in holds(second.id)] == ["consumed"]
    pin_clock(monkeypatch, at("2026-10-15", "21:05"))
    from live.errors import Conflict

    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.seat", {"id": str(second.id)})
    assert caught.value.code == "reservation.table_not_free"
    assert Reservation.objects.get(pk=second.id).status == "confirmed"
    assert Reservation.objects.get(pk=second.id).table_session_id is None
    assert Reservation.objects.get(pk=first.id).table_session_id == seated.table_session_id


def test_seating_at_a_table_out_of_service_says_so(terrace):
    out = book(table_id=str(terrace.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    run("table.table.update", {"id": str(terrace.id), "blocked": True})
    from live.errors import Conflict

    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.seat", {"id": str(out.id)})
    assert (caught.value.code, caught.value.message) == (
        "reservation.table_unavailable",
        "Table 5 (Terrace) cannot be booked: it is blocked or out of service.",
    )
    assert Reservation.objects.get(pk=out.id).status == "confirmed"


@pytest.mark.parametrize("change", ["inactive", "deleted", "zone_inactive"])
def test_confirming_with_a_table_out_of_service_is_refused(terrace, change):
    # TABLE-F25: Tables does not hold a table out of service; a reservation confirmed there would hold nothing.
    out = book(table_id=str(terrace.id))
    if change == "inactive":
        terrace.is_active = False
        terrace.save()
    elif change == "deleted":
        terrace.is_deleted = True
        terrace.save()
    else:
        terrace.zone.is_active = False
        terrace.zone.save()
    from live.errors import Conflict

    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.confirm", {"id": str(out.id)})
    assert caught.value.code == "reservation.table_unavailable"
    assert Reservation.objects.get(pk=out.id).status == "pending"
    assert holds(out.id) == []
