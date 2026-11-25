"""The hours of a range of days: up to 366 of them, between 1900 and 2200 (a 422 under the field, never a 500)."""

import datetime as dt

import pytest

from apps.schedule.schemas.hours import HoursRangeIn

from .test_schemas_fields import errors


def test_the_hours_of_a_range_take_up_to_366_days_and_one_day_alone():
    one = HoursRangeIn.model_validate({"date_from": "2026-08-17"})
    assert one.date_to == dt.date(2026, 8, 17)
    HoursRangeIn.model_validate({"date_from": "2026-01-01", "date_to": "2027-01-01"})
    assert errors(HoursRangeIn, date_from="2026-01-01", date_to="2027-01-02") == {
        "date_to": "At most 366 days at once."
    }
    assert errors(HoursRangeIn, date_from="2026-08-17", date_to="2026-08-16") == {
        "date_to": "The end date cannot be before the start date."
    }


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"date_from": "0001-01-01"}, "date_from"),
        ({"date_from": "1899-12-31"}, "date_from"),
        ({"date_from": "2200-12-31", "date_to": "9999-12-31"}, "date_to"),
        ({"date_from": "9999-12-31"}, "date_from"),
    ],
)
def test_the_hours_of_a_range_stay_between_1900_and_2200(data, field):
    assert errors(HoursRangeIn, **data) == {field: "Choose a date between 1900 and 2200."}


def test_the_first_and_last_days_of_the_range_are_fine():
    HoursRangeIn.model_validate({"date_from": "1900-01-01"})
    HoursRangeIn.model_validate({"date_from": "2200-12-31"})
