"""The days of the week as the Hub says them, Monday = 0 as ``datetime.date.weekday()``: CLDR's names with a capital
(«Jueves»), never a list of our own to translate.

A model field that stores a day takes ``weekdays`` as its ``choices`` and a schema declares it as ``Weekday``: with
both, the assistant's card names the day («Viernes») instead of its number. Migrations point at ``weekdays`` by its
path: moving or renaming it breaks them.
"""

from typing import Annotated

from babel.dates import get_day_names
from django.utils.text import capfirst
from django.utils.translation import get_language
from pydantic import Field

from base.business import babel_locale

#: A day of the week in a schema: one of its seven numbers. Declared as a closed list (``enum``) without making the
#: check strict, so a query string's «4» is still read as 4.
Weekday = Annotated[int, Field(ge=0, le=6, json_schema_extra={"enum": list(range(7))})]


def weekday_name(day: int, language: str | None = None) -> str:
    """The day ``day`` in ``language``, or in the active one."""
    return capfirst(get_day_names("wide", locale=babel_locale(language or get_language()))[day])


def weekdays() -> list[tuple[int, str]]:
    """The seven days as a field's ``choices``: a callable, so they are said in the language active when read."""
    return [(day, weekday_name(day)) for day in range(7)]
