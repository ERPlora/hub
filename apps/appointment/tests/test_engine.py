"""The diary's rules without a database (engine.py): whether a time can be booked and why not, the free
times of a day, the business's clock, and the dates a series repeats on.

Cases from the current product's tests (`availability*.test.py`, `create_overlap`, `busy_agenda_booking`,
`recurring_*`, `series_*`) and from its WORKFLOW (APPOINTMENTS-F02, F13, F14), on our own data.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from apps.appointment import engine
from apps.appointment.engine import (
    Agenda,
    BusinessDay,
    Pattern,
    Period,
    Rules,
    StaffDay,
)

MADRID = ZoneInfo("Europe/Madrid")
MONDAY = dt.date(2026, 10, 19)
SUNDAY = dt.date(2026, 10, 18)
#: «Now» of the tests: the Friday before, at noon.
NOW = dt.datetime(2026, 10, 16, 12, 0, tzinfo=MADRID)


def at(day: dt.date, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm), tzinfo=MADRID)


def naive(day: dt.date, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm))


def t(hhmm: str) -> dt.time:
    return dt.time.fromisoformat(hhmm)


def open_day(day: dt.date, *spans: tuple[str, str]) -> BusinessDay:
    """``day`` governed by a rule with these wall-clock spans (``("22:00", "02:00")`` crosses midnight)."""
    out = []
    for start, end in spans:
        begin, finish = naive(day, start), naive(day, end)
        if finish <= begin:
            finish += dt.timedelta(days=1)
        out.append((begin, finish))
    return BusinessDay(day, restricted=True, spans=tuple(out))


def agenda(
    *,
    business=(),
    staff=None,
    blocks=(),
    busy=(),
    **rules,
) -> Agenda:
    return Agenda(
        zone=MADRID,
        rules=Rules(**rules),
        business={day.date: day for day in business},
        staff=None if staff is None else {day.date: day for day in staff},
        blocks=list(blocks),
        busy=list(busy),
    )


def verdict(
    diary: Agenda,
    start: dt.datetime,
    minutes: int = 30,
    *,
    customer: bool = False,
    now=NOW,
):
    return engine.verdict(
        diary, start, start + dt.timedelta(minutes=minutes), now=now, customer=customer
    )


# The business's hours (Schedules)


def test_a_time_inside_an_opening_span_fits_up_to_the_closing_minute():
    diary = agenda(business=[open_day(MONDAY, ("09:00", "14:00"), ("16:00", "20:00"))])
    assert verdict(diary, at(MONDAY, "09:00")) is None
    assert verdict(diary, at(MONDAY, "13:30")) is None  # ends exactly at closing
    assert verdict(diary, at(MONDAY, "13:45")) == "outside_schedule"
    assert verdict(diary, at(MONDAY, "14:30")) == "outside_schedule"  # the lunch gap
    assert verdict(diary, at(MONDAY, "08:30")) == "outside_schedule"


def test_a_closed_day_refuses_and_a_day_without_any_rule_refuses_nothing():
    closed = BusinessDay(MONDAY, restricted=True, spans=())
    assert verdict(agenda(business=[closed]), at(MONDAY, "10:00")) == "outside_schedule"
    # No rule at all reaches the day (Schedules answers `none`): as the current product, anything goes.
    assert (
        verdict(
            agenda(business=[BusinessDay(MONDAY, restricted=False)]),
            at(MONDAY, "03:00"),
        )
        is None
    )
    assert verdict(agenda(), at(MONDAY, "03:00")) is None


def test_the_small_hours_of_the_eves_overnight_span_are_open():
    eve = open_day(SUNDAY, ("22:00", "02:00"))
    closed_monday = BusinessDay(MONDAY, restricted=True, spans=())
    diary = agenda(business=[eve, closed_monday])
    assert verdict(diary, at(MONDAY, "01:00")) is None
    assert verdict(diary, at(MONDAY, "01:45")) == "outside_schedule"
    assert (
        verdict(diary, at(SUNDAY, "23:45")) is None
    )  # crosses midnight inside the span


# The professional's hours (Staff)


def test_with_a_schedule_the_booking_fits_inside_what_is_left_of_the_shift():
    shift = StaffDay(
        MONDAY,
        has_schedule=True,
        available=((t("10:00"), t("14:00")), (t("15:00"), t("19:00"))),
    )
    diary = agenda(staff=[shift])
    assert verdict(diary, at(MONDAY, "10:00")) is None
    assert (
        verdict(diary, at(MONDAY, "13:45")) == "outside_staff_hours"
    )  # into the break
    assert verdict(diary, at(MONDAY, "09:30")) == "outside_staff_hours"
    # A day the schedule leaves off (no shift) is a day off.
    assert verdict(
        agenda(staff=[StaffDay(MONDAY, has_schedule=True)]), at(MONDAY, "10:00")
    ) == ("outside_staff_hours")


def test_without_a_schedule_only_an_approved_absence_refuses():
    free = StaffDay(MONDAY, has_schedule=False)
    assert verdict(agenda(staff=[free]), at(MONDAY, "07:00")) is None
    whole_day = StaffDay(MONDAY, has_schedule=False, absences=((None, None),))
    assert (
        verdict(agenda(staff=[whole_day]), at(MONDAY, "10:00")) == "outside_staff_hours"
    )
    doctor = StaffDay(MONDAY, has_schedule=False, absences=((t("11:00"), t("12:00")),))
    assert verdict(agenda(staff=[doctor]), at(MONDAY, "10:30"), 30) is None
    assert (
        verdict(agenda(staff=[doctor]), at(MONDAY, "10:45"), 30)
        == "outside_staff_hours"
    )
    assert verdict(agenda(staff=[doctor]), at(MONDAY, "12:00"), 30) is None


def test_a_professional_cannot_take_a_booking_that_crosses_midnight_on_a_shift():
    shift = StaffDay(MONDAY, has_schedule=True, available=((t("16:00"), t("23:59")),))
    assert (
        verdict(agenda(staff=[shift]), at(MONDAY, "23:30"), 60) == "outside_staff_hours"
    )


# Blocks and other appointments


def test_a_blocked_period_refuses_what_touches_it():
    block = Period(at(MONDAY, "12:00"), at(MONDAY, "13:00"), label="Training")
    diary = agenda(blocks=[block])
    assert verdict(diary, at(MONDAY, "11:45")) == "blocked"
    assert verdict(diary, at(MONDAY, "11:30")) is None  # ends as the block starts
    assert verdict(diary, at(MONDAY, "13:00")) is None


def test_another_appointment_of_the_professional_is_an_overlap_unless_the_front_desk_may_overlap():
    taken = Period(at(MONDAY, "10:00"), at(MONDAY, "10:30"), id="a1", label="Lucía")
    # Overlaps off: a hard block, even at the front desk.
    assert verdict(agenda(busy=[taken], allow_overlap=False), at(MONDAY, "10:15")) == "overlap"
    assert verdict(agenda(busy=[taken]), at(MONDAY, "10:30")) is None
    assert (
        verdict(agenda(busy=[taken], allow_overlap=True), at(MONDAY, "10:15")) is None
    )
    # The customer never books on top of another appointment.
    assert (
        verdict(
            agenda(busy=[taken], allow_overlap=True), at(MONDAY, "10:15"), customer=True
        )
        == "overlap"
    )
    assert engine.overlapping(
        agenda(busy=[taken]), at(MONDAY, "10:15"), at(MONDAY, "10:45")
    ) == [taken]


# Notice, advance and the past


def test_the_front_desk_books_in_the_past_and_inside_the_notice_the_customer_does_not():
    diary = agenda(min_notice=120)
    soon = NOW + dt.timedelta(minutes=30)
    past = NOW - dt.timedelta(hours=1)
    assert verdict(diary, soon) is None
    assert verdict(diary, past) is None
    assert verdict(diary, soon, customer=True) == "too_soon"
    assert verdict(diary, past, customer=True) == "in_past"


def test_the_maximum_advance_counts_days_inclusive_and_zero_lifts_it():
    last = NOW.date() + dt.timedelta(days=90)
    assert verdict(agenda(max_advance_days=90), at(last, "18:00")) is None
    assert (
        verdict(agenda(max_advance_days=90), at(last + dt.timedelta(days=1), "09:00"))
        == "too_far"
    )
    assert (
        verdict(agenda(max_advance_days=0), at(last + dt.timedelta(days=900), "09:00"))
        is None
    )


def test_a_booking_that_does_not_end_after_it_starts_is_invalid():
    assert engine.verdict(
        agenda(), at(MONDAY, "10:00"), at(MONDAY, "10:00"), now=NOW, customer=False
    ) == ("invalid_start")


def test_the_hours_rank_above_a_block_and_an_overlap():
    closed = BusinessDay(MONDAY, restricted=True, spans=())
    diary = agenda(
        business=[closed],
        blocks=[Period(at(MONDAY, "10:00"), at(MONDAY, "12:00"))],
        busy=[Period(at(MONDAY, "10:00"), at(MONDAY, "11:00"))],
    )
    assert verdict(diary, at(MONDAY, "10:00")) == "outside_schedule"
    assert (
        verdict(agenda(blocks=diary.blocks, busy=diary.busy), at(MONDAY, "10:00"))
        == "blocked"
    )


# Free times


def starts(free: list[engine.Slot]) -> list[str]:
    return [f"{slot.start.astimezone(MADRID):%H:%M}" for slot in free]


def test_free_times_step_through_the_calendar_window_and_keep_what_fits_whole():
    diary = agenda(
        business=[open_day(MONDAY, ("09:00", "11:00"))],
        busy=[Period(at(MONDAY, "09:30"), at(MONDAY, "10:00"))],
        allow_overlap=False,
        calendar_start_hour=8,
        calendar_end_hour=20,
        slot_interval=30,
    )
    assert starts(engine.slots(diary, MONDAY, 30, now=NOW, customer=False)) == [
        "09:00",
        "10:00",
        "10:30",
    ]
    # An hour long: only 10:00 fits whole before closing.
    assert starts(engine.slots(diary, MONDAY, 60, now=NOW, customer=False)) == ["10:00"]


def test_free_times_never_pass_the_end_of_the_calendar_window():
    diary = agenda(calendar_start_hour=18, calendar_end_hour=20, slot_interval=30)
    assert starts(engine.slots(diary, MONDAY, 60, now=NOW, customer=False)) == [
        "18:00",
        "18:30",
        "19:00",
    ]


def test_the_front_desk_sees_the_hours_inside_the_notice_marked_but_never_the_past():
    today = NOW.date()
    diary = agenda(
        min_notice=60, calendar_start_hour=11, calendar_end_hour=14, slot_interval=30
    )
    desk = engine.slots(diary, today, 30, now=NOW, customer=False)
    assert starts(desk) == ["12:00", "12:30", "13:00", "13:30"]
    assert [slot.within_notice for slot in desk] == [True, True, False, False]
    assert starts(engine.slots(diary, today, 30, now=NOW, customer=True)) == [
        "13:00",
        "13:30",
    ]


def test_with_overlaps_allowed_the_front_desk_still_sees_a_taken_hour_the_customer_does_not():
    busy = [Period(at(MONDAY, "10:00"), at(MONDAY, "11:00"))]
    diary = agenda(
        busy=busy,
        allow_overlap=True,
        calendar_start_hour=10,
        calendar_end_hour=11,
        slot_interval=30,
    )
    assert starts(engine.slots(diary, MONDAY, 30, now=NOW, customer=False)) == [
        "10:00",
        "10:30",
    ]
    assert starts(engine.slots(diary, MONDAY, 30, now=NOW, customer=True)) == []


# The business's clock


def test_a_wall_time_is_read_on_the_business_clock_and_an_instant_shown_on_it():
    moment = engine.aware(naive(MONDAY, "10:00"), MADRID)
    assert moment.utcoffset() == dt.timedelta(hours=2)
    assert engine.wall(moment.astimezone(dt.UTC), MADRID) == naive(MONDAY, "10:00")


def test_a_wall_time_the_clock_change_skips_does_not_exist():
    spring = dt.date(2027, 3, 28)  # Europe/Madrid jumps from 02:00 to 03:00
    with pytest.raises(engine.NonexistentTime):
        engine.aware(naive(spring, "02:30"), MADRID)
    # The repeated hour of autumn is its first time.
    autumn = engine.aware(naive(dt.date(2026, 10, 25), "02:30"), MADRID)
    assert autumn.utcoffset() == dt.timedelta(hours=2)


def test_free_times_skip_the_hour_the_clock_change_skips():
    spring = dt.date(2027, 3, 28)
    diary = agenda(calendar_start_hour=1, calendar_end_hour=4, slot_interval=30)
    now = dt.datetime(2027, 3, 1, tzinfo=MADRID)
    assert starts(engine.slots(diary, spring, 30, now=now, customer=False)) == [
        "01:00",
        "01:30",
        "03:00",
        "03:30",
    ]


# Series (RFC 5545 through dateutil)


def pattern(
    frequency: str, start: dt.date, *, day_of_week=None, end=None, count=None
) -> Pattern:
    return Pattern(frequency, day_of_week, start, end, count)


def test_a_weekly_series_starts_on_the_first_of_its_weekday_from_its_start_date():
    wednesday = dt.date(2026, 10, 21)
    dates, upcoming = engine.dates(
        pattern("weekly", wednesday, day_of_week=0), until=dt.date(2026, 11, 10)
    )
    assert dates == [dt.date(2026, 10, 26), dt.date(2026, 11, 2), dt.date(2026, 11, 9)]
    assert upcoming == dt.date(2026, 11, 16)


def test_a_fortnightly_series_counts_two_weeks_from_its_first_date_and_a_daily_one_every_day():
    dates, _ = engine.dates(
        pattern("biweekly", MONDAY, day_of_week=2), until=dt.date(2026, 11, 30)
    )
    assert dates == [dt.date(2026, 10, 21), dt.date(2026, 11, 4), dt.date(2026, 11, 18)]
    daily, _ = engine.dates(
        pattern("daily", MONDAY), until=MONDAY + dt.timedelta(days=2)
    )
    assert daily == [
        MONDAY,
        MONDAY + dt.timedelta(days=1),
        MONDAY + dt.timedelta(days=2),
    ]


def test_a_monthly_series_keeps_its_day_and_takes_the_last_one_of_a_short_month():
    dates, _ = engine.dates(
        pattern("monthly", dt.date(2027, 1, 31)), until=dt.date(2027, 5, 1)
    )
    assert dates == [
        dt.date(2027, 1, 31),
        dt.date(2027, 2, 28),
        dt.date(2027, 3, 31),
        dt.date(2027, 4, 30),
    ]
    leap, _ = engine.dates(
        pattern("monthly", dt.date(2028, 1, 30)), until=dt.date(2028, 3, 1)
    )
    assert leap == [dt.date(2028, 1, 30), dt.date(2028, 2, 29)]


def test_the_number_of_appointments_counts_from_the_start_and_the_end_date_is_included():
    rule = pattern("weekly", MONDAY, day_of_week=0, count=3)
    assert engine.dates(rule, until=MONDAY + dt.timedelta(days=100)) == (
        [MONDAY, MONDAY + dt.timedelta(weeks=1), MONDAY + dt.timedelta(weeks=2)],
        None,
    )
    ends = pattern("weekly", MONDAY, day_of_week=0, end=MONDAY + dt.timedelta(weeks=1))
    assert engine.dates(ends, until=MONDAY + dt.timedelta(days=100))[0] == [
        MONDAY,
        MONDAY + dt.timedelta(weeks=1),
    ]


def test_a_date_belongs_to_the_pattern_and_the_dates_before_a_cut_are_counted():
    rule = pattern("weekly", MONDAY, day_of_week=0)
    assert engine.contains(rule, MONDAY + dt.timedelta(weeks=3))
    assert not engine.contains(rule, MONDAY + dt.timedelta(days=1))
    assert not engine.contains(rule, MONDAY - dt.timedelta(weeks=1))
    assert engine.count_before(rule, MONDAY + dt.timedelta(weeks=2)) == 2
    assert engine.first_date(
        pattern("weekly", dt.date(2026, 10, 21), day_of_week=0)
    ) == dt.date(2026, 10, 26)
