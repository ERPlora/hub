"""The hours of a range (SCHEDULE-F11, the appointment book's contract): each day with its rule and its spans."""

import datetime as dt

from apps.schedule.schemas.hours import HoursRangeIn

from .conftest import HUB_DB, make_day, make_override, make_special_day
from .test_queries import is_open, run

pytestmark = HUB_DB


def hours(date_from, date_to=None):
    return run(
        "schedule.hours.for_range",
        HoursRangeIn(
            date_from=dt.date.fromisoformat(date_from),
            date_to=date_to and dt.date.fromisoformat(date_to),
        ),
    )


def test_the_hours_of_each_day_of_a_range_with_its_rule_and_spans(empty_week):
    make_day(0, ("10:00", "14:00"), ("22:00", "02:00"))
    make_day(1, closed=True)
    christmas = make_special_day("2026-08-19", "Local holiday", ("10:00", "13:00"))
    summer = make_override("2026-08-20", "2026-08-21", "Inventory")
    answer = hours("2026-08-17", "2026-08-23")
    assert answer.timezone == "Europe/Madrid"
    assert [(day.date, day.source, day.is_closed, day.name) for day in answer.days] == [
        (dt.date(2026, 8, 17), "weekly", False, ""),
        (dt.date(2026, 8, 18), "weekly", True, ""),
        (dt.date(2026, 8, 19), "special_day", False, "Local holiday"),
        (dt.date(2026, 8, 20), "override", True, "Inventory"),
        (dt.date(2026, 8, 21), "override", True, "Inventory"),
        (dt.date(2026, 8, 22), "none", False, ""),
        (dt.date(2026, 8, 23), "none", False, ""),
    ]
    monday = answer.days[0]
    assert [(s.start, s.end) for s in monday.spans] == [
        (dt.datetime(2026, 8, 17, 10), dt.datetime(2026, 8, 17, 14)),
        (dt.datetime(2026, 8, 17, 22), dt.datetime(2026, 8, 18, 2)),
    ]
    assert answer.days[1].spans == []
    assert (
        answer.days[2].rule_id == christmas.id and answer.days[3].rule_id == summer.id
    )
    assert answer.days[5].rule_id is None and answer.days[5].spans == []


def test_one_day_alone_and_a_yearly_special_day_of_another_year():
    make_special_day("2020-12-25", "Christmas", recurring_yearly=True)
    answer = hours("2026-12-25")
    assert [(day.date, day.source, day.name) for day in answer.days] == [
        (dt.date(2026, 12, 25), "special_day", "Christmas")
    ]


def test_a_24_hours_day_spans_until_the_next_midnight(empty_week):
    make_day(5, ("00:00", "00:00"))
    assert [(s.start, s.end) for s in hours("2026-08-22").days[0].spans] == [
        (dt.datetime(2026, 8, 22, 0), dt.datetime(2026, 8, 23, 0))
    ]


def test_the_ends_of_the_allowed_calendar_answer(empty_week):
    # 1900-01-01 is a Monday; 2200-12-31 a Wednesday. An overnight interval at either end stays a date.
    make_day(0, ("22:00", "02:00"))
    make_day(2, ("22:00", "02:00"))
    first = hours("1900-01-01")
    assert [(s.start, s.end) for s in first.days[0].spans] == [(dt.datetime(1900, 1, 1, 22), dt.datetime(1900, 1, 2, 2))]
    last = hours("2200-12-31")
    assert [(s.start, s.end) for s in last.days[0].spans] == [(dt.datetime(2200, 12, 31, 22), dt.datetime(2201, 1, 1, 2))]
    assert is_open("1900-01-01T23:00").is_open
    assert is_open("2200-12-31T23:30+00:00").code == "overnight_open"
