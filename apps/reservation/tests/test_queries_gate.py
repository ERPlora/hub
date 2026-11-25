"""What the gate reads of a day: the business's opening hours (Schedules) and what keeps a table."""

import datetime as dt

from django.utils import timezone

from apps.reservation.queries.business import window_of
from apps.reservation.queries.gate import booked_windows, hours_of

from .conftest import HUB_DB, THURSDAY, TOMORROW, ctx_for, make_reservation, make_slot, make_table, run, set_week_hours

pytestmark = HUB_DB


def test_a_closed_day_after_a_night_past_midnight_says_closed_not_the_eve_hours():
    # Friday 13:00–01:00 belongs to Friday, as every hours listing shows it: Saturday, closed in
    # Schedules, has no hours of its own, the same as its slots and the booking judge it.
    set_week_hours([("13:00", "01:00")], days=[4])
    set_week_hours([], days=[5])
    make_slot(5, "16:00", "23:00")
    day = run("reservation.availability.day", {"date": "2026-10-17"})
    assert (day.hours_restricted, day.spans, day.slots[0].in_hours) == (True, [], False)


def test_the_default_week_nobody_confirmed_does_not_restrict():
    # Schedules ships Monday to Friday 09:00–18:00 until the business saves or confirms its week: a
    # restaurant that never opened Schedules must still book its dinners.
    make_slot(THURSDAY, "20:00", "23:30")
    day = run("reservation.availability.day", {"date": "2026-10-15"})
    assert (day.hours_restricted, day.spans, day.slots[0].in_hours) == (False, [], True)
    assert hours_of(ctx_for(), TOMORROW).restricted is False


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
        held = booked_windows(five.pk, window_of(dt.date(2030, 3, 5), dt.time(22), 60))
    assert (row.free, row.taken_from, row.taken_until) == (False, dt.time(23, 0), dt.time(23, 0))
    assert [(kept.date, kept.time) for kept, _ in held] == [(dt.date(2030, 3, 4), dt.time(23))]
