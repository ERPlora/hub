"""What several schemas of the schedule app share: messages, limits of the calendar, field types, descriptions,
the titles and marks of the assistant's card, the page of a list and its checks of dates."""

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, ValidationInfo

from base.schemas.assistant import names

T = TypeVar("T")
RANGE_BACKWARDS = _("The end date cannot be before the start date.")
OUT_OF_CALENDAR = _("Choose a date between 1900 and 2200.")

#: The days «is it open?» and the hours of a range answer for: far beyond any booking, and far from the
#: ends of Python's calendar (year 1, year 9999), where a day more or an hour of offset overflows.
MIN_DATE = dt.date(1900, 1, 1)
MAX_DATE = dt.date(2200, 12, 31)

Direction = Literal["asc", "desc"]
Source = Literal["special_day", "override", "weekly", "none"]

# Descriptions shared by several schemas.
D_IS_CLOSED = (
    "True: closed all day (its intervals are ignored). False: open in its intervals."
)
D_INTERVALS = (
    "The opening intervals, one per stretch (a split shift is two: 10:00–14:00 and 17:00–20:00); at most 12, "
    "in any order. Required when it is open."
)
D_SEARCH = "Free text to search."

# How the assistant's card names a datum the models do not (its Spanish in this app's catalog), as the screens say it.
T_INTERVALS = gettext_noop("Opening intervals")
T_SPECIAL_DAY = gettext_noop("Special day")
T_OVERRIDE = gettext_noop("Override")
D_DIRECTION = "Sort direction: asc or desc."

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a special day by its name and a temporary change by its reason, as the screens' «Delete»
# dialog says them.
A_SPECIAL_DAY = names("schedule.special_day.get")
A_OVERRIDE = names("schedule.override.get", name=("reason",))
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Search = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Reference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class PageIn(Schema):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, for the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int = Field(description="Rows that match, over all pages.")
    limit: int
    offset: int


class NoParamsIn(Schema):
    model_config = ConfigDict(extra="forbid")


class DeletedOut(Schema):
    id: UUID


class ByIdIn(Schema):
    id: UUID = Field(description="The record's id.")


def _not_before(field: str) -> Any:
    """A ``…_to`` / ``end_date`` field that may not come before ``field``."""

    def check(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get(field)
        if value is not None and start is not None and value < start:
            raise ValueError(str(RANGE_BACKWARDS))
        return value

    return classmethod(check)


def _in_calendar(day: dt.date | None) -> dt.date | None:
    """A day between ``MIN_DATE`` and ``MAX_DATE``, or ``ValueError`` (a 422 under the field)."""
    if day is not None and not MIN_DATE <= day <= MAX_DATE:
        raise ValueError(str(OUT_OF_CALENDAR))
    return day


def _out_of_calendar_text(text: str | None) -> bool:
    """A moment whose own date (as written) already lies out of ``MIN_DATE`` … ``MAX_DATE``."""
    try:
        return not MIN_DATE <= dt.date.fromisoformat((text or "").strip()[:10]) <= MAX_DATE
    except ValueError:
        return False
