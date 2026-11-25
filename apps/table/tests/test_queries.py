"""The table app's reads as a whole: the live floor (each table's status computed from its checks, its block and its
holds, and the checks of a split table) and who may read what.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import PermissionDenied

from .conftest import (
    HUB_DB,
    A,
    ctx_for,
    end_order,
    make_customer,
    make_hold,
    make_session,
    make_table,
    make_zone,
    open_check,
    pin_clock,
    run,
)

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]

EMPLOYEE = "hub_employee"


def table_row(table) -> dict:
    return run("table.table.get", {"id": str(table.id)}).model_dump()


def test_a_table_nobody_sits_at_is_available_with_its_seats():
    table = make_table("4", zone=make_zone(), capacity=6)
    row = table_row(table)
    assert (
        row["status"],
        row["capacity"],
        row["guests"],
        row["since"],
        row["checks"],
        row["hold"],
    ) == (
        "available",
        6,
        None,
        None,
        [],
        None,
    )


def test_an_occupied_table_says_who_sits_since_when_and_who_serves():
    # The plan projects who serves and since when, and the guests.
    table = make_table("4", zone=make_zone())
    session = make_session(table, guests_count=3, minutes_ago=35, waiter_name="Luis")
    row = table_row(table)
    assert (row["status"], row["guests"], row["waiter_name"]) == ("occupied", 3, "Luis")
    assert row["since"] == session.opened_at
    assert [check["id"] for check in row["checks"]] == [session.id]


def test_a_table_whose_check_sales_already_ended_is_free_again():
    # What Sales did is read on every read (charged whole, or voided), before any relay delivers it.
    table = make_table("4", zone=make_zone())
    order = open_check("Table 4")
    make_session(table, order_id=order.id)
    assert table_row(table)["status"] == "occupied"
    end_order(order.id)
    assert table_row(table)["status"] == "available"


def test_a_check_without_a_sales_check_still_occupies_its_table():
    table = make_table("4", zone=make_zone())
    make_session(table, order_id=None)
    assert table_row(table)["status"] == "occupied"


def test_a_blocked_table_is_blocked_unless_somebody_still_sits_there():
    zone = make_zone()
    blocked = make_table("1", zone=zone, blocked=True)
    seated = make_table("2", zone=zone, blocked=True)
    make_session(seated)
    assert (table_row(blocked)["status"], table_row(seated)["status"]) == (
        "blocked",
        "occupied",
    )


def test_a_reservation_paints_its_table_from_an_hour_before():
    zone = make_zone()
    soon = make_table("1", zone=zone)
    later = make_table("2", zone=zone)
    make_hold(soon, starts_in=30, label="Ana", party_size=4, ref="soon")
    make_hold(later, starts_in=180, label="Luis", ref="later")
    near, far = table_row(soon), table_row(later)
    assert (
        near["status"],
        near["hold"]["label"],
        near["hold"]["party_size"],
        near["hold"]["reserving"],
    ) == (
        "reserved",
        "Ana",
        4,
        True,
    )
    # Later today: the table stays free and shows its next reservation.
    assert (far["status"], far["hold"]["label"], far["hold"]["reserving"]) == (
        "available",
        "Luis",
        False,
    )


def test_late_in_the_evening_today_ends_at_the_business_midnight(monkeypatch):
    # 22:30 in Madrid: a reservation at 23:30 is still today's; one at 00:30 is tomorrow's.
    pin_clock(monkeypatch, dt.datetime(2026, 10, 14, 20, 30, tzinfo=dt.UTC))
    zone = make_zone()
    tonight, after = make_table("1", zone=zone), make_table("2", zone=zone)
    make_hold(tonight, starts_in=60, ref="tonight", label="Ana")
    make_hold(after, starts_in=120, ref="after", label="Luis")
    assert (table_row(tonight)["hold"]["label"], table_row(after)["hold"]) == ("Ana", None)


def test_a_reservation_of_another_day_or_already_over_is_not_shown():
    zone = make_zone()
    tomorrow = make_table("1", zone=zone)
    over = make_table("2", zone=zone)
    hours_to_midnight = (
        timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        + dt.timedelta(days=1)
        - timezone.now()
    )
    make_hold(
        tomorrow,
        starts_in=int(hours_to_midnight.total_seconds() // 60) + 90,
        ref="tomorrow",
    )
    make_hold(over, starts_in=-200, lasts=120, ref="over")
    assert (table_row(tomorrow)["hold"], table_row(tomorrow)["status"]) == (
        None,
        "available",
    )
    assert (table_row(over)["hold"], table_row(over)["status"]) == (None, "available")


def test_a_blocked_table_is_not_painted_reserved_and_an_erased_name_says_so():
    zone = make_zone()
    blocked = make_table("1", zone=zone, blocked=True)
    make_hold(blocked, starts_in=10, ref="b", label="Ana")
    erased = make_table("2", zone=zone)
    make_hold(erased, starts_in=10, ref="e", label="", customer_id=uuid.uuid7())
    assert table_row(blocked)["status"] == "blocked"
    shown = table_row(erased)["hold"]
    assert (shown["label"], shown["erased"]) == ("", True)


def test_the_earliest_reservation_of_today_is_the_one_shown():
    table = make_table("1", zone=make_zone())
    make_hold(table, starts_in=120, ref="second", label="Luis")
    make_hold(table, starts_in=20, ref="first", label="Ana")
    assert table_row(table)["hold"]["label"] == "Ana"


def test_a_split_table_lists_both_checks_oldest_first_with_the_customer_of_each():
    table = make_table("4", zone=make_zone())
    first_order, second_order = open_check("Table 4"), open_check("Table 4")
    first = make_session(table, order_id=first_order.id, minutes_ago=20, guests_count=3)
    second = make_session(
        table, order_id=second_order.id, minutes_ago=5, guests_count=1, split_from=first
    )
    ana = make_customer("Ana García")
    run(
        "customer.order.link",
        {"order_id": str(first_order.id), "customer_id": str(ana.id)},
        system_context(A),
    )
    row = table_row(table)
    assert row["guests"] == 4
    assert [
        (c["id"], c["customer_name"], c["split_from_id"]) for c in row["checks"]
    ] == [
        (first.id, "Ana García", None),
        (second.id, None, first.id),
    ]


def test_whoever_reads_the_checks_reads_their_lines_and_the_holds_whoever_reads_the_tables():
    booking = uuid.uuid7()
    make_hold(make_table("2"), source="reservation", ref=str(booking), label="Pedro")
    assert run("table.hold.by_reservation", {"reservation_id": str(booking)}, ctx_for(EMPLOYEE)).label == "Pedro"
    for name, data in (
        ("table.hold.by_reservation", {"reservation_id": str(booking)}),
        ("table.session.line", {"id": str(uuid.uuid7())}),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, ctx_for(permissions=set()))


def test_an_employee_reads_the_room_but_a_stranger_reads_nothing():
    make_table("1")
    assert run("table.table.list", {}, ctx_for(EMPLOYEE)).total == 1
    with pytest.raises(PermissionDenied):
        run("table.table.list", {}, ctx_for(permissions=set()))
