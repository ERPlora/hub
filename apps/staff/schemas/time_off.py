"""Schemas of the time off: asking for it, answering it, and its lists."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.staff.schemas.fields import (
    END_BEFORE_START,
    TIME_ORDER,
    MemberOfIn,
    Page,
    PageIn,
    Search,
    Text500,
    _both_ways,
    _text,
)
from base.schemas.assistant import names

TIMES_REQUIRED = _("A half-day absence needs a start and an end time.")

LeaveType = Literal["vacation", "sick", "personal", "training", "other"]
TimeOffStatus = Literal["pending", "approved", "rejected", "cancelled"]

TIME_OFF_SORTS = (
    "start_date",
    "end_date",
    "member_name",
    "leave_type",
    "status",
    "is_full_day",
    "approved_at",
    "id",
)

TimeOffSort = _both_ways(TIME_OFF_SORTS)

Text2000 = _text(2000)

A_TIME_OFF = names("staff.time_off.get", name=("label",))
TIME_OFF = gettext_noop("Time off")


class TimeOffFieldsIn(Schema):
    """Whole days, or the same hours on each day of the range; a full day drops any hours sent."""

    leave_type: LeaveType = Field(
        "vacation",
        description="vacation, sick (sick leave), personal, training or other.",
    )
    start_date: dt.date = Field(description="First day off (YYYY-MM-DD).")
    end_date: dt.date = Field(
        description="Last day off (YYYY-MM-DD), not before the first."
    )
    is_full_day: bool = Field(
        True,
        description="true = whole days; false = only the hours below, on each day.",
    )
    start_time: dt.time | None = Field(
        None,
        validate_default=True,
        description="From what time (HH:MM), for a part-day absence.",
    )
    end_time: dt.time | None = Field(
        None,
        validate_default=True,
        description="Until what time (HH:MM), for a part-day absence.",
    )
    reason: Text500 = Field(
        "", description="Why (optional; private, only for managers and the person)."
    )
    notes: Text2000 = Field(
        "", description="Notes (optional; private, only for managers and the person)."
    )

    @field_validator("end_date")
    @classmethod
    def _ends_after_it_starts(cls, value: dt.date, info: ValidationInfo) -> dt.date:
        start = info.data.get("start_date")
        if start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def _hours_of_a_part_day(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if info.data.get("is_full_day", True):
            return value
        if value is None:
            raise ValueError(str(TIMES_REQUIRED))
        start = info.data.get("start_time")
        if info.field_name == "end_time" and start is not None and value <= start:
            raise ValueError(str(TIME_ORDER))
        return value

    @model_validator(mode="after")
    def _full_day_has_no_hours(self):
        if self.is_full_day:
            self.start_time = self.end_time = None
        return self


# The member goes after the fields (the order the assistant reads them in): the bases are collected last to first.
class TimeOffIn(MemberOfIn, TimeOffFieldsIn):
    pass


class TimeOffRequestIn(TimeOffFieldsIn):
    """The caller's own time off: the member is the one linked to the caller's user."""


class TimeOffRefIn(Schema):
    id: UUID = Field(title=TIME_OFF, description="The time-off request's id.", json_schema_extra=A_TIME_OFF)


class TimeOffListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the person's name."
    )
    member_id: UUID | None = Field(
        None, description="Only this staff member's time off."
    )
    status: TimeOffStatus | None = Field(
        None, description="pending, approved, rejected or cancelled."
    )
    leave_type: LeaveType | None = Field(
        None, description="vacation, sick, personal, training or other."
    )
    is_full_day: bool | None = Field(
        None, description="Only whole days (true) or only part days (false)."
    )
    approved_by_id: UUID | None = Field(
        None, description="Only the time off approved by this business user."
    )
    date_from: dt.date | None = Field(
        None, description="Only the time off that reaches this day or later."
    )
    date_to: dt.date | None = Field(
        None, description="Only the time off that starts on this day or earlier."
    )
    start_date_from: dt.date | None = Field(
        None, description="Only the time off starting on or after this day."
    )
    start_date_to: dt.date | None = Field(
        None, description="Only the time off starting on or before this day."
    )
    end_date_from: dt.date | None = Field(
        None, description="Only the time off ending on or after this day."
    )
    end_date_to: dt.date | None = Field(
        None, description="Only the time off ending on or before this day."
    )
    sort: TimeOffSort = Field(
        "-start_date", description="Column to sort by; a leading '-' sorts descending."
    )


class TodayIn(PageIn):
    pass


class MyTimeOffIn(PageIn):
    pass


class TimeOffOut(Schema):
    id: UUID
    member_id: UUID
    member_name: str
    leave_type: LeaveType
    leave_type_label: str = Field(description="The type in the caller's language (e.g. Vacation).")
    start_date: dt.date
    end_date: dt.date
    is_full_day: bool
    start_time: dt.time | None
    end_time: dt.time | None
    status: TimeOffStatus
    approved_by_id: UUID | None = Field(description="The business user who approved it.")
    approved_at: dt.datetime | None


class TimeOffNamedOut(TimeOffOut):
    """A time-off request as the list says it, never with its reason, and how the card names it."""

    label: str = Field(description="Whose it is, of what kind and which days, in the caller's language.")


class TimeOffDetailOut(TimeOffOut):
    reason: str
    notes: str
    approved_by_name: str | None
    created_at: dt.datetime


TimeOffPage = Page[TimeOffOut]
TimeOffDetailPage = Page[TimeOffDetailOut]
