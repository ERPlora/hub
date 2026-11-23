"""The days of the week as the Hub says them (Monday = 0, as ``datetime.date.weekday()``): CLDR's names with a capital, in
the language asked or the active one. The same seven days are a model field's ``choices`` and a schema's closed list,
which is how the assistant's card names a day instead of printing its number."""

import pytest
from django.utils import translation
from ninja import Schema
from pydantic import ValidationError

from base.weekdays import Weekday, weekday_name, weekdays

SPANISH = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
ENGLISH = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class Day(Schema):
    day: Weekday


@pytest.mark.parametrize(("language", "names"), [("es", SPANISH), ("en", ENGLISH)])
def test_each_day_is_said_by_its_name_with_a_capital_in_the_language_asked(language, names):
    assert [weekday_name(day, language) for day in range(7)] == names


@pytest.mark.parametrize(("language", "names"), [("es", SPANISH), ("en", ENGLISH), ("es-es", SPANISH)])
def test_without_a_language_a_day_is_said_in_the_active_one(language, names):
    with translation.override(language):
        assert weekday_name(4) == names[4]


@pytest.mark.parametrize(("language", "names"), [("es", SPANISH), ("en", ENGLISH)])
def test_the_choices_are_the_seven_days_from_monday_said_when_read(language, names):
    """A callable, so a field that takes it says its days in the language active when they are read, not at import."""
    with translation.override(language):
        assert weekdays() == list(enumerate(names))


def test_a_schema_declares_a_day_as_the_closed_list_of_its_seven_numbers():
    prop = Day.model_json_schema()["properties"]["day"]
    assert prop["enum"] == list(range(7))
    assert (prop["type"], prop["minimum"], prop["maximum"]) == ("integer", 0, 6)


def test_a_day_sent_as_text_is_read_as_its_number_and_a_day_out_of_the_week_is_refused():
    """A query string sends every number as text: the closed list in the schema does not make the check strict."""
    assert Day(day="4").day == 4
    for wrong in (7, -1):
        with pytest.raises(ValidationError):
            Day(day=wrong)
