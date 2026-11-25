"""The intervals of a day: one rule, whichever form sends them, and each refusal under ``intervals``."""

import datetime as dt

import pytest
from django.utils import translation

from apps.schedule.schemas.intervals import IntervalIn, check_intervals
from apps.schedule.schemas.overrides import OverrideIn
from apps.schedule.schemas.special_days import SpecialDayIn
from apps.schedule.schemas.week import SetDayIn

from .test_schemas_fields import errors


def hours(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"open_time": start, "close_time": end} for start, end in pairs]


def test_an_open_day_takes_its_intervals_sorted():
    day = SetDayIn.model_validate(
        {"weekday": 1, "intervals": hours(("17:00", "20:00"), ("10:00", "14:00"))}
    )
    assert [(i.open_time, i.close_time) for i in day.intervals] == [
        (dt.time(10), dt.time(14)),
        (dt.time(17), dt.time(20)),
    ]
    assert day.is_closed is False


def test_a_closed_day_drops_its_intervals():
    day = SetDayIn.model_validate(
        {"weekday": 6, "is_closed": True, "intervals": hours(("10:00", "14:00"))}
    )
    assert day.intervals == []


@pytest.mark.parametrize(
    ("intervals", "message"),
    [
        ([], "An open day needs at least one opening interval."),
        (
            hours(("10:00", "10:00")),
            "An interval cannot open and close at the same time; 00:00–00:00 is open 24 hours.",
        ),
        (
            hours(("09:00", "14:00"), ("13:00", "18:00")),
            "Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash.",
        ),
    ],
)
def test_the_rules_of_the_intervals_land_under_intervals(intervals, message):
    assert errors(SetDayIn, weekday=0, intervals=intervals) == {"intervals": message}
    assert errors(
        SpecialDayIn,
        date="2026-12-24",
        name="Eve",
        is_closed=False,
        intervals=intervals,
    ) == {"intervals": message}
    assert errors(
        OverrideIn,
        start_date="2026-08-01",
        end_date="2026-08-31",
        reason="Summer",
        is_closed=False,
        intervals=intervals,
    ) == {"intervals": message}


def test_at_most_twelve_intervals():
    thirteen = hours(*[(f"{hour:02d}:00", f"{hour:02d}:30") for hour in range(13)])
    assert "intervals" in errors(SetDayIn, weekday=0, intervals=thirteen)


def test_overnight_and_24_hours_are_intervals_too():
    assert SetDayIn.model_validate(
        {"weekday": 4, "intervals": hours(("22:00", "02:00"))}
    ).intervals[0].close_time == dt.time(2)
    assert SetDayIn.model_validate(
        {"weekday": 5, "intervals": hours(("00:00", "00:00"))}
    ).intervals[0].open_time == dt.time(0)


def test_a_time_that_is_not_a_time_is_refused_under_its_field():
    assert "intervals.0.open_time" in errors(
        SetDayIn, weekday=0, intervals=hours(("25:00", "18:00"))
    )


def test_check_intervals_is_the_one_rule_for_every_form():
    assert (
        check_intervals(
            True, [IntervalIn(open_time=dt.time(9), close_time=dt.time(10))]
        )
        == []
    )
    with pytest.raises(ValueError, match="An open day needs"):
        check_intervals(False, [])


def test_the_messages_speak_spanish():
    with translation.override("es"):
        assert errors(SetDayIn, weekday=0, intervals=[]) == {
            "intervals": "Un día abierto necesita al menos un tramo horario."
        }
