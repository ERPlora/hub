"""The inbox of online bookings: its list, how a booking is named, cancelled and read, and what a delete answers."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.appointment.schemas.fields import AN_APPOINTMENT, OF_STATUS
from apps.customer.schemas.contact import EMAIL, PHONE
from apps.online_booking.schemas.fields import In, Page, Status, _text

SAY_WHICH_BOOKING = _("Say which booking: its number, or the customer's name, phone or email (and the day).")
END_BEFORE_START = _("The end cannot be before the start.")

# The assistant's card names the record a write acts on as the diary (Citas) names it, read as whoever asks and never
# by its id (base/assistant/cards.py ``REFERS``): a booking is an appointment of it, so it goes by its customer, day, hour and
# professional, as the inbox's «Cancel …'s booking (…)?» dialog says it; a service and a professional, by their names.
#: The word the bookings list calls one («Reserva»).
T_BOOKING = gettext_noop("Booking")

BookingSort = Literal[
    "booked_at", "start", "number", "customer_name", "staff_name", "status"
]
Dir = Literal["asc", "desc"]


class BookingListIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )
    search: _text(100) = Field(
        "",
        description="Text in the number, the customer's name (and her phone or email, for whoever sees them), a "
        "service or the professional.",
    )
    number: _text(24) | None = Field(
        None, description="Part of the appointment number (APT-…)."
    )
    customer_name: _text(100) | None = Field(
        None, description="Part of the customer's name."
    )
    service: _text(100) | None = Field(None, description="Part of a service's name.")
    staff_name: _text(100) | None = Field(
        None, description="Part of the professional's name."
    )
    status: Status | None = Field(
        None,
        description="Only this status: pending, confirmed, in_progress, completed, cancelled or no_show.",
    )
    date_from: dt.date | None = Field(
        None, description="Only bookings from this business day (YYYY-MM-DD)."
    )
    date_to: dt.date | None = Field(
        None,
        description="Only bookings up to this business day (included; YYYY-MM-DD).",
    )
    staff_id: UUID | None = Field(
        None, description="Only this professional's bookings."
    )
    sort: BookingSort = Field(
        "booked_at",
        description="Order by: booked_at (when it was booked, default), start, number, customer_name, staff_name "
        "or status.",
    )
    dir: Dir = Field("desc", description="asc or desc (default: the newest first).")

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if value is not None and start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value


class BookingRefIn(In):
    id: UUID | None = Field(
        None,
        title=T_BOOKING,
        description="The booking's id (its appointment's id).",
        json_schema_extra=AN_APPOINTMENT,
    )
    number: _text(24, 1) | None = Field(
        None,
        title=gettext_noop("No."),
        description="The appointment number (APT-YYYYMMDD-NNNN).",
    )
    customer: _text(200, 1) | None = Field(
        None,
        title=gettext_noop("Customer"),
        description="The customer as a person says it: her name (or part of it) or, for whoever sees them, her phone or her email.",
    )
    date: dt.date | None = Field(
        None,
        description="With the customer: the business day of the booking (YYYY-MM-DD); empty = her next one.",
    )

    @model_validator(mode="after")
    def _which(self):
        if self.id is None and self.number is None and self.customer is None:
            raise ValueError(str(SAY_WHICH_BOOKING))
        return self


class CancelIn(BookingRefIn):
    reason: _text(500) = Field(
        "", description="Why it is cancelled (optional; kept in its history)."
    )


class LineOut(Schema):
    service_id: UUID
    name: str = Field(description="The service's name when it was booked.")
    price: int = Field(description="Its price when it was booked, in cents.", json_schema_extra={"money": True})
    duration_minutes: int


class BookingRow(Schema):
    """An online booking as the inbox lists it: the appointment and how to reach the customer."""

    id: UUID = Field(description="The appointment's id.")
    number: str
    customer_id: UUID
    customer_name: str = Field(description="Empty when the customer's data was erased.")
    customer_phone: str | None = PHONE
    customer_email: str | None = EMAIL
    staff_id: UUID | None
    staff_name: str
    services: list[LineOut]
    service_names: str
    start: dt.datetime = Field(description="On the business's clock.")
    end: dt.datetime
    duration_minutes: int
    status: Status = Field(json_schema_extra=OF_STATUS)
    total: int = Field(description="The sum of its services' prices, in cents.", json_schema_extra={"money": True})
    notes: str = Field(description="The customer's note.")
    booked_at: dt.datetime
    via_page: bool = Field(
        description="Booked on the public page (it has the customer's link)."
    )
    sale_id: UUID | None
    order_id: UUID | None


class BookingOut(BookingRow):
    cancelled_at: dt.datetime | None
    cancellation_reason: str
    cancelled_by_customer: bool


class BookingPage(Page[BookingRow]):
    pass


class DeletedOut(Schema):
    id: UUID
    deleted: bool
