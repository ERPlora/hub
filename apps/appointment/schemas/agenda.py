"""The agenda: the short range of days it reads, its list and its lanes."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.appointment.schemas.appointments import AppointmentRow
from apps.appointment.schemas.fields import END_BEFORE_START, In, Page, Said, Status, _text

#: The longest range the agenda reads at once (two months: a week view and its neighbours).
MAX_RANGE_DAYS = 62

RANGE_TOO_LONG = _("Ask for at most 62 days at once.")

AppointmentSort = Literal[
    "start",
    "-start",
    "number",
    "-number",
    "customer_name",
    "-customer_name",
    "staff_name",
    "-staff_name",
    "status",
    "-status",
]


class DateRange(In):
    date_from: dt.date = Field(description="First business day (YYYY-MM-DD).")
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="Last business day (included; at most 62 days on); empty = the first.",
    )

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if value is None or start is None:
            return value
        if value < start:
            raise ValueError(str(END_BEFORE_START))
        if (value - start).days > MAX_RANGE_DAYS:
            raise ValueError(str(RANGE_TOO_LONG))
        return value


class AppointmentListIn(DateRange):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(0, ge=0, description="How many rows to skip.")
    staff_id: UUID | None = Field(
        None, description="Only this professional's appointments."
    )
    staff: Said | None = Field(
        None, description="Only this professional's appointments, by name."
    )
    unassigned: bool | None = Field(
        None, description="True: only the appointments without a professional."
    )
    customer_id: UUID | None = Field(
        None, description="Only this customer's appointments."
    )
    status: Status | None = Field(None, description="Only this status.")
    search: _text(100) = Field(
        "", description="Text in the number, the customer's name or a service."
    )
    sort: AppointmentSort = Field(
        "start",
        description="Order: start (default), number, customer, professional, status.",
    )


class AppointmentPage(Page[AppointmentRow]):
    timezone: str = Field(
        description="The business's time zone: every time is on its clock."
    )


class LaneOut(Schema):
    staff_id: UUID
    name: str
    color: str
    takes_bookings: bool = Field(
        description="False: no longer bookable (kept while it has appointments)."
    )


class LanesIn(DateRange):
    pass


class LanesOut(Schema):
    rows: list[LaneOut]
    unassigned: int = Field(
        description="Appointments without a professional in the range."
    )
    own_staff_id: UUID | None = Field(
        description="The caller's own staff record, if linked."
    )
    sees_everyone: bool = Field(
        description="False: the caller sees their own agenda only."
    )
    timezone: str
