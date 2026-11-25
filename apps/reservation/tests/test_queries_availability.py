"""A day's figures and slots, and the free tables of a day, time and party."""

import datetime as dt

from apps.reservation.queries.availability import day_availability
from apps.reservation.schemas.availability import DayIn

from .conftest import (
    CLOCKS_BACK,
    CLOCKS_FORWARD,
    HUB_DB,
    THURSDAY,
    TODAY,
    TOMORROW,
    ctx_for,
    make_blocked,
    make_reservation,
    make_slot,
    make_table,
    make_zone,
    run,
    set_week_hours,
)

pytestmark = HUB_DB


def test_a_day_counts_its_slots_like_the_gate_and_adds_up_its_covers():
    lunch = make_slot(THURSDAY, "13:00", "16:00", max_reservations=3)
    dinner = make_slot(THURSDAY, "20:00", "23:30", max_reservations=2, max_covers=10)
    make_slot(THURSDAY + 1, "20:00", "23:30")
    make_reservation(time="13:30", party_size=2, status="confirmed")
    make_reservation(time="14:00", party_size=4, status="cancelled")
    make_reservation(time="20:00", party_size=6, status="seated")
    make_reservation(time="21:00", party_size=3, status="completed")
    make_reservation(time="21:30", party_size=5, status="no_show")
    make_reservation(time="22:00", party_size=8, is_deleted=True)
    make_reservation(date=TODAY, time="21:00", party_size=2)
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.date, day.today, day.timezone, day.closed) == (
        TOMORROW,
        TODAY,
        "Europe/Madrid",
        False,
    )
    loads = {slot.id: slot for slot in day.slots}
    assert [slot.id for slot in day.slots] == [lunch.id, dinner.id]
    assert (
        loads[lunch.id].reserved,
        loads[lunch.id].covers,
        loads[lunch.id].available,
        loads[lunch.id].full,
    ) == (
        1,
        2,
        2,
        False,
    )
    assert (
        loads[dinner.id].reserved,
        loads[dinner.id].covers,
        loads[dinner.id].available,
        loads[dinner.id].full,
    ) == (
        2,
        9,
        0,
        True,
    )
    assert (day.reservations, day.covers) == (3, 11)


def test_a_day_without_a_date_is_the_business_today():
    assert run("reservation.availability.day").date == TODAY
    assert day_availability(ctx_for(), DayIn()).date == TODAY


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


def test_a_day_brings_the_business_hours_and_marks_the_slots_that_start_closed():
    set_week_hours([("13:00", "16:00")])
    lunch = make_slot(THURSDAY, "13:00", "16:00")
    dinner = make_slot(THURSDAY, "20:00", "23:30")
    day = run(
        "reservation.availability.day", {"date": "2026-10-15"}, ctx_for("hub_employee")
    )
    assert day.hours_restricted is True
    assert [(span.start, span.end) for span in day.spans] == [
        (dt.datetime(2026, 10, 15, 13, 0), dt.datetime(2026, 10, 15, 16, 0))
    ]
    in_hours = {slot.id: slot.in_hours for slot in day.slots}
    assert in_hours == {lunch.id: True, dinner.id: False}


def test_a_day_after_a_night_past_midnight_shows_only_its_own_hours():
    set_week_hours([("13:00", "01:00")], days=[4])
    set_week_hours([("13:00", "23:30")], days=[5])
    day = run("reservation.availability.day", {"date": "2026-10-17"})
    assert [(span.start, span.end) for span in day.spans] == [
        (dt.datetime(2026, 10, 17, 13, 0), dt.datetime(2026, 10, 17, 23, 30))
    ]


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
