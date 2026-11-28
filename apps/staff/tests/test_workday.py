"""A working day of a schedule sent without its hours takes the business's default working day (Staff › Settings), as
the schedule's window proposes it: its start, its end and its break in the middle of the day, the break's start rounded
down to the quarter hour (``scheduleForm.ts``'s ``proposedBreak``, the same cases)."""

import datetime as dt

import pytest
from live.errors import InvalidPayload

from apps.staff.schemas.schedules import DayIn
from apps.staff.workday import Workday, proposed_break, with_working_day, with_working_days

SALON = Workday(dt.time(10), dt.time(19), 60)


def hours(day: DayIn) -> tuple:
    return (day.start_time, day.end_time, day.break_start, day.break_end)


@pytest.mark.parametrize(
    ("workday", "expected"),
    [
        (Workday(dt.time(9), dt.time(18), 60), (dt.time(13), dt.time(14))),
        (Workday(dt.time(8), dt.time(16), 30), (dt.time(11, 45), dt.time(12, 15))),
        (Workday(dt.time(9), dt.time(18), 45), (dt.time(13), dt.time(13, 45))),
        (Workday(dt.time(7, 30), dt.time(15), 20), (dt.time(11), dt.time(11, 20))),
        (Workday(dt.time(8), dt.time(8, 50), 40), (dt.time(8), dt.time(8, 40))),
        (SALON, (dt.time(14), dt.time(15))),
    ],
)
def test_the_break_sits_in_the_middle_of_the_day(workday, expected):
    assert proposed_break(workday) == expected


@pytest.mark.parametrize(
    "workday",
    [Workday(dt.time(9), dt.time(18), 0), Workday(dt.time(9), dt.time(10), 60), Workday(dt.time(22), dt.time(6), 30)],
)
def test_no_break_for_0_minutes_nor_in_a_day_that_cannot_hold_it(workday):
    assert proposed_break(workday) == (None, None)


def test_a_day_without_its_hours_is_the_working_day_with_its_break():
    assert hours(with_working_day(DayIn(weekday=1), SALON)) == (dt.time(10), dt.time(19), dt.time(14), dt.time(15))


def test_a_day_with_its_hours_keeps_them_and_gets_no_break():
    day = DayIn(weekday=1, start_time="11:00", end_time="15:00")
    assert hours(with_working_day(day, SALON)) == (dt.time(11), dt.time(15), None, None)


def test_an_hour_not_said_is_the_working_days_and_no_break_is_proposed():
    assert hours(with_working_day(DayIn(weekday=1, start_time="11:00"), SALON)) == (dt.time(11), dt.time(19), None, None)
    assert hours(with_working_day(DayIn(weekday=1, end_time="15:00"), SALON)) == (dt.time(10), dt.time(15), None, None)


def test_a_break_said_without_the_hours_keeps_it_inside_the_working_day():
    day = DayIn(weekday=1, break_start="13:00", break_end="13:30")
    assert hours(with_working_day(day, SALON)) == (dt.time(10), dt.time(19), dt.time(13), dt.time(13, 30))


def test_midnight_is_an_hour_said():
    day = DayIn(weekday=1, start_time="00:00")
    assert with_working_day(day, SALON).start_time == dt.time(0)


def test_a_day_off_is_left_as_it_came():
    day = DayIn(weekday=6, is_working=False)
    assert with_working_day(day, SALON) == day


def test_a_week_says_under_its_day_what_the_working_day_makes_wrong():
    days = [DayIn(weekday=0), DayIn(weekday=1, start_time="20:00"), DayIn(weekday=2, break_start="08:00", break_end="09:00")]
    with pytest.raises(InvalidPayload) as refused:
        with_working_days(days, SALON)
    assert refused.value.fields == {"days.1.end_time": "The start time must be before the end time."}
    with pytest.raises(InvalidPayload) as refused:
        with_working_days([days[0], days[2]], SALON)
    assert refused.value.fields == {"days.1.break_end": "The break must fall inside the working hours."}
