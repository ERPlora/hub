"""The hours of a range of days, for the appointment book."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, ValidationInfo, field_validator

from apps.schedule.schemas.fields import RANGE_BACKWARDS, Source, _in_calendar
from apps.schedule.schemas.intervals import IntervalOut

RANGE_TOO_LONG = _("At most 366 days at once.")
MAX_RANGE_DAYS = 366


class HoursRangeIn(Schema):
    model_config = ConfigDict(extra="forbid")

    date_from: dt.date = Field(
        description="First day, YYYY-MM-DD, on the business's calendar (between 1900 and 2200)."
    )
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="Last day, YYYY-MM-DD (included); empty = the first day alone.",
    )

    @field_validator("date_from")
    @classmethod
    def _from_in_calendar(cls, value: dt.date) -> dt.date:
        return _in_calendar(value)

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        _in_calendar(value)
        start = info.data.get("date_from")
        if start is None:
            return value
        end = value or start
        if end < start:
            raise ValueError(str(RANGE_BACKWARDS))
        if (end - start).days >= MAX_RANGE_DAYS:
            raise ValueError(str(RANGE_TOO_LONG))
        return end


class SpanOut(Schema):
    start: dt.datetime = Field(
        description="Opening, the business's wall-clock date and time."
    )
    end: dt.datetime = Field(
        description="Closing (excluded); the next day when it crosses midnight."
    )


class DayHoursOut(Schema):
    date: dt.date
    source: Source = Field(
        description="Which rule governs the day: special_day, override, weekly or none."
    )
    rule_id: UUID | None
    name: str = Field(
        description="The special day's name or the change's reason; empty for the week."
    )
    is_closed: bool
    intervals: list[IntervalOut]
    spans: list[SpanOut] = Field(
        description="The intervals as wall-clock date and time; a booking fits inside one."
    )


class HoursRangeOut(Schema):
    timezone: str
    days: list[DayHoursOut]
