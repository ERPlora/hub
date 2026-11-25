"""The inputs of the availability: a day is the business's today unless one is given, and the free tables are
asked for a day and a time, within the book's bounds."""

import datetime as dt

from apps.reservation.schemas.availability import DayIn, TablesIn

from .conftest import errors

AT_NINE = {"date": "2026-10-15", "time": "21:00"}


def test_a_day_is_the_business_s_today_unless_one_is_given():
    assert DayIn.model_validate({}).date is None
    assert DayIn.model_validate({"date": "2026-10-15"}).date == dt.date(2026, 10, 15)
    assert "colour" in errors(DayIn, {"colour": "red"})


def test_the_free_tables_are_asked_for_a_day_and_a_time_within_the_book_s_bounds():
    asked = TablesIn.model_validate(AT_NINE)
    assert (asked.date, asked.time) == (dt.date(2026, 10, 15), dt.time(21))
    assert (asked.duration_minutes, asked.party_size, asked.exclude_id, asked.search) == (None, None, None, None)
    assert set(errors(TablesIn, {})) == {"date", "time"}
    assert "party_size" in errors(TablesIn, {**AT_NINE, "party_size": 0})
    assert "duration_minutes" in errors(TablesIn, {**AT_NINE, "duration_minutes": 24 * 60 + 1})
    assert "search" in errors(TablesIn, {**AT_NINE, "search": "x" * 101})
