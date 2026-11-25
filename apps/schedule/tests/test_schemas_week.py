"""A day of the week, by number or by name."""

import pytest

from apps.schedule.schemas.week import SetDayIn

from .test_schemas_fields import errors


@pytest.mark.parametrize(
    ("value", "weekday"),
    [
        (0, 0),
        ("6", 6),
        ("monday", 0),
        ("Lunes", 0),
        ("miércoles", 2),
        ("miercoles", 2),
        ("Sun", 6),
        ("sábado", 5),
        ("el lunes", 0),
        ("El Sábado", 5),
        ("the sunday", 6),
    ],
)
def test_a_weekday_is_a_number_or_its_name_in_english_or_spanish(value, weekday):
    assert (
        SetDayIn.model_validate({"weekday": value, "is_closed": True}).weekday
        == weekday
    )


@pytest.mark.parametrize("value", [7, -1, "someday", ""])
def test_a_weekday_out_of_the_week_is_refused(value):
    assert "weekday" in errors(SetDayIn, weekday=value, is_closed=True)
