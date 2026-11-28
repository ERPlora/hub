"""Schemas of the working schedules: each person's week, its days, its break and when it applies."""

import datetime as dt
from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, ValidationInfo, field_validator

from apps.staff.schemas.fields import (
    D_MEMBER,
    D_MEMBER_ID,
    TIME_ORDER,
    MemberId,
    MemberName,
    Page,
    PageIn,
    Text100,
    _said_by,
)
from base.schemas.assistant import names
from base.weekdays import Weekday

BREAK_PAIR = _("The break needs a start and an end, or neither.")
BREAK_INSIDE = _("The break must fall inside the working hours.")
NO_DAYS = _("A schedule needs at least one working day with hours.")
WEEKDAY_REPEATED = _("Each weekday can appear only once.")
SCHEDULE_RANGE = _("The schedule's validity ends before it starts.")

A_SCHEDULE = names("staff.schedule.detail", name=("label",))
SCHEDULE = gettext_noop("Schedule")


class DayIn(Schema):
    """One weekday (Monday = 0): a stretch with an optional break inside it. An hour it does not say is the business's
    default working day (Staff settings)."""

    weekday: Weekday = Field(description="Day of the week: 0 Monday … 6 Sunday.")
    start_time: dt.time | None = Field(
        None,
        description="Start of the working day (HH:MM), only when the person says it; empty: the business's default "
        "working day (Staff settings).",
    )
    end_time: dt.time | None = Field(
        None,
        description="End of the working day (HH:MM), after the start, only when the person says it; empty: the "
        "business's default working day.",
    )
    break_start: dt.time | None = Field(
        None,
        description="Start of the break (HH:MM), inside the working day; a day without any of its hours takes the "
        "default working day's break.",
    )
    break_end: dt.time | None = Field(
        None,
        validate_default=True,
        description="End of the break (HH:MM); with its start, or neither.",
    )
    is_working: bool = Field(
        True,
        description="false = the person does not work that day (its hours are ignored).",
    )

    @field_validator("end_time")
    @classmethod
    def _ends_after_it_starts(cls, value: dt.time | None, info: ValidationInfo) -> dt.time | None:
        start = info.data.get("start_time")
        if start is not None and value is not None and value <= start:
            raise ValueError(str(TIME_ORDER))
        return value

    @field_validator("break_end")
    @classmethod
    def _break_inside(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if (
            "break_start" not in info.data
        ):  # break_start itself is invalid: its own error says so
            return value
        start = info.data["break_start"]
        if (start is None) != (value is None):
            raise ValueError(str(BREAK_PAIR))
        day_start, day_end = info.data.get("start_time"), info.data.get("end_time")
        if value is not None and day_start is not None and day_end is not None:
            if not day_start <= start < value <= day_end:
                raise ValueError(str(BREAK_INSIDE))
        return value


def _a_week(value: list[DayIn]) -> list[DayIn]:
    if not any(day.is_working for day in value):
        raise ValueError(str(NO_DAYS))
    weekdays = [day.weekday for day in value]
    if len(set(weekdays)) != len(weekdays):
        raise ValueError(str(WEEKDAY_REPEATED))
    return value


Week = Annotated[list[DayIn], AfterValidator(_a_week)]
D_DAYS = "The week: one entry per weekday, at least one working day; a weekday not sent is a day off."
#: How the schedule form names the week (the assistant's card names the datum by it).
WEEK = gettext_noop("Week")


def _valid_range(value: dt.date | None, info: ValidationInfo) -> dt.date | None:
    start = info.data.get("effective_from")
    if value is not None and start is not None and value < start:
        raise ValueError(str(SCHEDULE_RANGE))
    return value


class ScheduleIn(Schema):
    name: Text100 = Field(
        "",
        description="Name of the schedule, only when the person gives one; empty: the Hub names it as its screens "
        "do, in the person's language.",
    )
    is_default: bool = Field(
        True, description="Whether it is the person's usual schedule (only one is)."
    )
    effective_from: dt.date | None = Field(
        None, description="First day it applies (YYYY-MM-DD); empty = always."
    )
    effective_until: dt.date | None = Field(
        None, description="Last day it applies (YYYY-MM-DD); empty = no end."
    )
    days: Week = Field(title=WEEK, description=D_DAYS)
    member_id: MemberId = None
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    _valid_range = field_validator("effective_until")(_valid_range)
    _named = _said_by("member_id")


class ScheduleUpdateIn(Schema):
    """Replaces the week. The other fields keep their value when not sent; ``null`` clears a date."""

    id: UUID = Field(title=SCHEDULE, description="The schedule's id.", json_schema_extra=A_SCHEDULE)
    name: Text100 | None = Field(
        None, description="New name; empty: the name the Hub gives a schedule without one, in the person's language."
    )
    is_default: bool | None = Field(
        None, description="Whether it becomes (or stops being) the usual schedule."
    )
    effective_from: dt.date | None = Field(
        None, description="First day it applies; null = always."
    )
    effective_until: dt.date | None = Field(
        None, description="Last day it applies; null = no end."
    )
    days: Week = Field(title=WEEK, description=D_DAYS)

    _valid_range = field_validator("effective_until")(_valid_range)


class ScheduleRefIn(Schema):
    id: UUID = Field(title=SCHEDULE, description="The schedule's id.", json_schema_extra=A_SCHEDULE)


class SetActiveIn(Schema):
    id: UUID = Field(title=SCHEDULE, description="The schedule's id.", json_schema_extra=A_SCHEDULE)
    is_active: bool = Field(
        description="false: the schedule never governs a day; true: it does again."
    )


class ScheduleListIn(PageIn):
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    _named = _said_by("member_id")


class DayOut(Schema):
    weekday: int = Field(description="0 Monday … 6 Sunday.")
    start_time: dt.time
    end_time: dt.time
    break_start: dt.time | None
    break_end: dt.time | None


class ScheduleOut(Schema):
    id: UUID
    member_id: UUID
    name: str
    is_default: bool
    effective_from: dt.date | None
    effective_until: dt.date | None
    is_active: bool
    days: list[DayOut] = Field(
        description="The working days; a weekday missing is a day off."
    )


class ScheduleDetailOut(ScheduleOut):
    label: str = Field(description="Whose it is and its name: what tells it from another person's of that name.")


SchedulePage = Page[ScheduleOut]
