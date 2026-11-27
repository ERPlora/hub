"""The app's settings: lengths, notice, cancellation and the calendar's hours."""

from typing import Annotated

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.appointment.schemas.fields import In, Minutes
from base.schemas.assistant import no_limit

CALENDAR_UPSIDE_DOWN = _("The calendar has to end after it starts.")

#: Days ahead one may book, up to a year; 0 is no limit.
AdvanceDays = Annotated[int, Field(ge=0, le=365, json_schema_extra=no_limit())]


class SettingsIn(In):
    default_duration: Minutes | None = Field(
        None, description="Minutes of a booking with no service length."
    )
    min_booking_notice: int | None = Field(
        None,
        ge=0,
        le=10080,
        description="Minutes ahead the customer must book (the front desk books for now).",
    )
    max_advance_booking: AdvanceDays | None = Field(
        None,
        description="Days ahead one may book (up to a year); 0 = no limit (a series then books 90 days).",
    )
    allow_overlapping: bool | None = Field(
        None,
        description="True: the front desk is warned and may book anyway; false: a hard block.",
    )
    allow_customer_cancellation: bool | None = Field(
        None, description="The customer may cancel her appointment."
    )
    cancellation_notice_hours: int | None = Field(
        None, ge=0, le=720, description="Hours before the start she may still cancel."
    )
    calendar_start_hour: int | None = Field(
        None, ge=0, le=23, description="The calendar starts at this hour."
    )
    calendar_end_hour: int | None = Field(
        None, ge=1, le=24, description="The calendar ends at this hour."
    )
    slot_interval: int | None = Field(
        None, ge=5, le=240, description="Minutes between free times."
    )
    auto_confirm_online: bool | None = Field(
        None,
        description="The customer's own bookings are born confirmed (false: pending, to review).",
    )

    @model_validator(mode="after")
    def _window(self):
        start, end = self.calendar_start_hour, self.calendar_end_hour
        if start is not None and end is not None and end <= start:
            raise ValueError(str(CALENDAR_UPSIDE_DOWN))
        return self


class SettingsOut(Schema):
    default_duration: int
    min_booking_notice: int
    max_advance_booking: int
    allow_overlapping: bool
    allow_customer_cancellation: bool
    cancellation_notice_hours: int
    calendar_start_hour: int
    calendar_end_hour: int
    slot_interval: int
    auto_confirm_online: bool
    timezone: str
