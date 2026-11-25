"""Special days: one, a bulk of them, how one is named and the list of them."""

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, ValidationInfo, field_validator

from apps.schedule.engine import MAX_INTERVALS
from apps.schedule.schemas.fields import (
    A_SPECIAL_DAY,
    D_DIRECTION,
    D_INTERVALS,
    D_IS_CLOSED,
    D_SEARCH,
    T_INTERVALS,
    T_SPECIAL_DAY,
    Direction,
    Name,
    Page,
    PageIn,
    Reference,
    Search,
    _not_before,
)
from apps.schedule.schemas.intervals import IntervalIn, IntervalOut, _CheckedIntervals, _intervals_field
from base.schemas.assistant import IN_OWN_WORDS

WHICH_SPECIAL_DAY = _("Say which special day: its id, its name or its date.")
MAX_BULK = 366
#: Intervals a day of the bulk may carry before the whole list is refused (the cap of a day is 12).
MAX_BULK_INTERVALS = 100
D_SPECIAL_DAY_ID = (
    "The id of the special day; or say it by name or date in special_day."
)
D_SPECIAL_DAY_REF = "The special day by its name (Christmas) or its date (YYYY-MM-DD), when the id is not given."
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class SpecialDayOut(Schema):
    id: UUID
    date: dt.date
    name: str
    is_closed: bool
    recurring_yearly: bool
    notes: str
    intervals: list[IntervalOut]


SpecialDayPage = Page[SpecialDayOut]


class SpecialDayFields(Schema):
    """A special day as the bulk takes it: the rules of its intervals are checked day by day."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date = Field(description="The date, YYYY-MM-DD (a real calendar date).")
    name: Name = Field(description="Its name (Christmas, Local holiday).", json_schema_extra=IN_OWN_WORDS)
    is_closed: bool = Field(True, description=D_IS_CLOSED + " Closed by default.")
    # The bulk checks the 12-interval cap day by day (a day over it is skipped, `invalid_hours`); this
    # bound only stops an absurd payload, refused whole.
    intervals: list[IntervalIn] = Field(
        default_factory=list, max_length=MAX_BULK_INTERVALS, description=D_INTERVALS
    )
    recurring_yearly: bool = Field(
        False,
        description="True: it repeats on the same day and month every year (also the years before).",
    )
    notes: Notes = Field("", description="Optional notes.")


class SpecialDayIn(_CheckedIntervals, SpecialDayFields):
    intervals: list[IntervalIn] = _intervals_field()


class SpecialDayRefIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        None, title=T_SPECIAL_DAY, description=D_SPECIAL_DAY_ID, json_schema_extra=A_SPECIAL_DAY
    )
    special_day: Reference | None = Field(
        None, validate_default=True, description=D_SPECIAL_DAY_REF
    )

    @field_validator("special_day")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None and "id" in info.data and info.data["id"] is None:
            raise ValueError(str(WHICH_SPECIAL_DAY))
        return value


class SpecialDayPatchIn(SpecialDayRefIn):
    """Only what is sent changes; sent intervals replace them all."""

    date: dt.date | None = Field(None, description="The new date, YYYY-MM-DD.")
    name: Name | None = Field(None, description="The new name.")
    is_closed: bool | None = Field(None, description=D_IS_CLOSED)
    intervals: list[IntervalIn] | None = Field(
        None, max_length=MAX_INTERVALS, title=T_INTERVALS, description=D_INTERVALS
    )
    recurring_yearly: bool | None = Field(
        None, description="True: it repeats on the same day and month every year."
    )
    notes: Notes | None = Field(None, description="The new notes.")


class BulkSpecialDayIn(Schema):
    model_config = ConfigDict(extra="forbid")

    special_days: list[SpecialDayFields] = Field(
        min_length=1,
        max_length=MAX_BULK,
        title=gettext_noop("Special days"),
        description="The special days to create, 1 to 366.",
    )


class BulkSkippedOut(Schema):
    index: int = Field(description="Position of the day in the list sent, from 0.")
    date: dt.date
    code: Literal["already_exists", "invalid_hours"] = Field(
        description="Why it was skipped."
    )
    message: str = Field(description="The reason, in the reader's language.")


class BulkCreatedOut(Schema):
    created: list[UUID] = Field(
        description="The ids of the special days created, in the order sent."
    )
    skipped: list[BulkSkippedOut] = Field(
        description="The days that were not created, with their reason."
    )


class SpecialDayListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Name or notes.")
    date_from: dt.date | None = Field(
        None, description="Only the special days on or after this date."
    )
    date_to: dt.date | None = Field(
        None, description="Only the special days on or before this date."
    )
    name: Search | None = Field(
        None, description="Only the special days whose name contains this."
    )
    is_closed: bool | None = Field(
        None, description="True: only the closed ones; false: only the open ones."
    )
    recurring_yearly: bool | None = Field(
        None, description="True: only the yearly ones; false: only the one-off ones."
    )
    sort: Literal["date", "name", "is_closed", "recurring_yearly", "id"] = Field(
        "date", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=D_DIRECTION)

    _date_to = field_validator("date_to")(_not_before("date_from"))
