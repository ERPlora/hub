"""A service day (``reservation.availability.day``) and the free tables for a party (``reservation.availability.tables``)."""

import datetime as dt

from django.utils import timezone

from .conftest import (
    CLOCKS_BACK,
    CLOCKS_FORWARD,
    HUB_DB,
    TODAY,
    ctx_for,
    make_blocked,
    make_reservation,
    make_table,
    make_zone,
    run,
)

pytestmark = HUB_DB


def test_a_day_without_a_date_is_the_business_today():
    assert run("reservation.availability.day").date == TODAY


def test_a_day_says_its_blocks_and_whether_it_is_closed():
    make_blocked(
        reason="Private event",
        is_full_day=False,
        blocked_from=dt.time(20),
        blocked_until=dt.time(22),
    )
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.closed, [block.reason for block in day.blocks]) == (
        False,
        ["Private event"],
    )
    make_blocked(reason="Holiday", blocked_from=None)
    assert run("reservation.availability.day", {"date": "2026-10-15"}).closed is True


def test_the_free_tables_are_the_ones_in_service_without_a_live_reservation_then():
    room = make_zone("Room")
    shut = make_zone("Closed room", is_active=False)
    two = make_table("2", zone=room, capacity=2)
    ten = make_table("10", zone=room, capacity=6)
    four = make_table("4", zone=room, capacity=4)
    make_table("6", zone=room, blocked=True)
    make_table("7", zone=room, is_active=False)
    make_table("8", zone=room, is_deleted=True)
    make_table("9", zone=shut)
    make_reservation(time="20:00", table=four, status="confirmed")
    make_reservation(time="21:00", table=ten, status="completed")
    make_reservation(time="21:00", table=two, status="cancelled")
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:00", "party_size": 3},
        ctx_for("hub_employee"),
    )
    shown = [(row.number, row.free, row.fits) for row in result.rows]
    assert shown == [("10", True, True), ("2", True, False), ("4", False, True)]
    taken = result.rows[2]
    assert (taken.taken_from, taken.taken_until, taken.label, taken.capacity) == (
        dt.time(20),
        dt.time(22),
        "4 (Room)",
        4,
    )


def test_the_free_tables_count_a_stay_in_real_time_the_nights_the_clocks_change():
    five = make_table("5")

    def table_at(day: dt.date, time: str):
        return run(
            "reservation.availability.tables",
            {"date": day.isoformat(), "time": time, "duration_minutes": 60},
        ).rows[0]

    # 01:37 summer time plus 90 real minutes ends at 02:07 of the second pass (winter time).
    make_reservation(
        date=CLOCKS_BACK, time="01:37", duration_minutes=90, table=five, status="confirmed"
    )
    assert table_at(CLOCKS_BACK, "03:00").free
    taken = table_at(CLOCKS_BACK, "02:30")
    assert (taken.free, taken.taken_from, taken.taken_until) == (
        False,
        dt.time(1, 37),
        dt.time(2, 7),
    )
    # 01:00 winter time plus 90 real minutes ends at 03:30 summer time.
    make_reservation(
        date=CLOCKS_FORWARD, time="01:00", duration_minutes=90, table=five, status="confirmed"
    )
    taken = table_at(CLOCKS_FORWARD, "03:00")
    assert (taken.free, taken.taken_until) == (False, dt.time(3, 30))
    assert table_at(CLOCKS_FORWARD, "03:30").free


def test_the_free_tables_look_around_the_business_day_not_the_utc_one_west_of_utc():
    """West of UTC an evening is already the next UTC day: the neighbours of a stay are the days of
    the business's wall clock, so a table kept since the night before is still found."""
    five = make_table("5")
    with timezone.override("America/New_York"):
        make_reservation(
            date=dt.date(2030, 3, 4),
            time="23:00",
            duration_minutes=24 * 60,
            table=five,
            status="confirmed",
        )
        row = run(
            "reservation.availability.tables",
            {"date": "2030-03-05", "time": "22:00", "duration_minutes": 60},
        ).rows[0]
    assert (row.free, row.taken_from, row.taken_until) == (False, dt.time(23, 0), dt.time(23, 0))


def test_a_reservation_being_changed_does_not_take_its_own_table():
    four = make_table("4")
    mine = make_reservation(time="21:00", table=four, status="confirmed")
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:30", "exclude_id": str(mine.id)},
    )
    assert [(row.number, row.free) for row in result.rows] == [("4", True)]


def test_the_free_tables_search_by_number_name_or_zone():
    make_table("1", zone=make_zone("Terrace"))
    make_table("2", zone=make_zone("Bar"))
    result = run(
        "reservation.availability.tables",
        {"date": "2026-10-15", "time": "21:00", "search": "terr"},
    )
    assert [row.number for row in result.rows] == ["1"]
