"""The week: its seven days, and a day of the week by its number or by its name."""

import unicodedata
from typing import Annotated, Any
from uuid import UUID

from ninja import Field, Schema
from pydantic import BeforeValidator, ConfigDict

from apps.schedule.schemas.fields import D_IS_CLOSED
from apps.schedule.schemas.intervals import IntervalIn, IntervalOut, _CheckedIntervals, _intervals_field
from base import weekdays

_WEEKDAY_NAMES = {
    0: ("monday", "mon", "lunes", "lun"),
    1: ("tuesday", "tue", "martes", "mar"),
    2: ("wednesday", "wed", "miercoles", "mie"),
    3: ("thursday", "thu", "jueves", "jue"),
    4: ("friday", "fri", "viernes", "vie"),
    5: ("saturday", "sat", "sabado", "sab"),
    6: ("sunday", "sun", "domingo", "dom"),
}
_BY_NAME = {name: weekday for weekday, names in _WEEKDAY_NAMES.items() for name in names}


def _plain(text: str) -> str:
    """Lowercase, without accents or spaces at the ends («Miércoles» → «miercoles»)."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


_ARTICLES = ("el ", "the ")


def _weekday(value: Any) -> Any:
    """A name of the week («lunes», «Monday»), also as spoken: «el lunes», «the Monday»."""
    if not isinstance(value, str):
        return value
    name = _plain(value)
    for article in _ARTICLES:
        name = name.removeprefix(article)
    return _BY_NAME.get(name.strip(), value)


Weekday = Annotated[weekdays.Weekday, BeforeValidator(_weekday)]


class WeekDayOut(Schema):
    weekday: int = Field(description="0 = Monday … 6 = Sunday.")
    name: str = Field(description="The day's name in the reader's language.")
    id: UUID | None = Field(
        description="The row of the day; null when the day is not set."
    )
    is_set: bool = Field(
        description="False: nothing configured for that day (not open, not closed)."
    )
    is_closed: bool
    intervals: list[IntervalOut]


class WeekOut(Schema):
    week_starts_on: int = Field(
        description="1 = Monday … 7 = Sunday: the order of ``days``."
    )
    confirmed: bool = Field(
        description="False while the week is the default one nobody has saved or confirmed."
    )
    timezone: str = Field(
        description="The business's time zone (IANA), the clock the hours are read with."
    )
    days: list[WeekDayOut] = Field(
        description="The seven days, from the one the week starts on."
    )


class SetDayIn(_CheckedIntervals, Schema):
    model_config = ConfigDict(extra="forbid")

    weekday: Weekday = Field(
        description="The day of the week: 0 = Monday … 6 = Sunday, or its name (monday, lunes)."
    )
    is_closed: bool = Field(False, description=D_IS_CLOSED)
    intervals: list[IntervalIn] = _intervals_field()
