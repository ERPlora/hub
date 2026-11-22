"""Schemas of a staff member's availability, day by day: their shifts and the approved absences."""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.staff.schemas.fields import END_BEFORE_START, MAX_AVAILABILITY_DAYS, RANGE_TOO_LONG, MemberOfIn


class AvailabilityIn(MemberOfIn):
    date_from: dt.date = Field(
        description="First day (YYYY-MM-DD), in the business's calendar."
    )
    date_to: dt.date = Field(
        description="Last day (YYYY-MM-DD); at most 731 days after the first."
    )

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date, info: ValidationInfo) -> dt.date:
        start = info.data.get("date_from")
        if start is not None:
            if value < start:
                raise ValueError(str(END_BEFORE_START))
            if (value - start).days >= MAX_AVAILABILITY_DAYS:
                raise ValueError(str(RANGE_TOO_LONG))
        return value


class IntervalOut(Schema):
    start: dt.time
    end: dt.time


class AbsenceOut(Schema):
    """An approved absence covering the day, without its type or reason."""

    is_full_day: bool
    start_time: dt.time | None
    end_time: dt.time | None


class AvailabilityDayOut(Schema):
    date: dt.date
    schedule_id: UUID | None = Field(
        description="The schedule that governs the day; null = none (do not refuse on shifts)."
    )
    shifts: list[IntervalOut] = Field(
        description="The working stretches of the day, split by the break."
    )
    time_off: list[AbsenceOut] = Field(
        description="Approved absences covering the day."
    )
    available: list[IntervalOut] = Field(
        description="The shifts minus the approved absences."
    )


class AvailabilityOut(Schema):
    member_id: UUID
    days: list[AvailabilityDayOut]
