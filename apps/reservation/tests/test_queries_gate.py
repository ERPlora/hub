"""What the gate reads, as a day shows it: its slots counted as booking counts them, and the business's opening
hours that govern it."""

import datetime as dt

from .conftest import (
    HUB_DB,
    THURSDAY,
    TODAY,
    TOMORROW,
    ctx_for,
    make_reservation,
    make_slot,
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


def test_a_closed_day_after_a_night_past_midnight_says_closed_not_the_eve_hours():
    # Friday 13:00–01:00 belongs to Friday, as every hours listing shows it: Saturday, closed in
    # Schedules, has no hours of its own, the same as its slots and the booking judge it.
    set_week_hours([("13:00", "01:00")], days=[4])
    set_week_hours([], days=[5])
    make_slot(5, "16:00", "23:00")
    day = run("reservation.availability.day", {"date": "2026-10-17"})
    assert (day.hours_restricted, day.spans, day.slots[0].in_hours) == (True, [], False)


def test_a_day_after_a_night_past_midnight_shows_only_its_own_hours():
    set_week_hours([("13:00", "01:00")], days=[4])
    set_week_hours([("13:00", "23:30")], days=[5])
    day = run("reservation.availability.day", {"date": "2026-10-17"})
    assert [(span.start, span.end) for span in day.spans] == [
        (dt.datetime(2026, 10, 17, 13, 0), dt.datetime(2026, 10, 17, 23, 30))
    ]


def test_the_default_week_nobody_confirmed_does_not_restrict():
    # Schedules ships Monday to Friday 09:00–18:00 until the business saves or confirms its week: a
    # restaurant that never opened Schedules must still book its dinners.
    make_slot(THURSDAY, "20:00", "23:30")
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.hours_restricted, day.spans, day.slots[0].in_hours) == (False, [], True)
