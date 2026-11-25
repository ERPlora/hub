"""One appointment: how it is named and how it reads back, its history, a customer's visits and what the team is told
of it."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.appointment.schemas.fields import AN_APPOINTMENT, T_APPOINTMENT, In, Page, Source, Status, _text
from apps.appointment.schemas.references import CustomerOf, ServiceRefIn, _named
from apps.customer.schemas.contact import EMAIL, PHONE

SAY_WHICH_APPOINTMENT = _("Say which appointment: its id, or its number.")

HistoryAction = Literal[
    "created",
    "confirmed",
    "started",
    "completed",
    "cancelled",
    "no_show",
    "rescheduled",
    "staff_changed",
    "service_changed",
    "unassigned",
    "charged",
    "uncharged",
    "deleted",
    "restored",
]


class AppointmentRefIn(In):
    id: UUID | None = Field(
        None, title=T_APPOINTMENT, description="The appointment's id.", json_schema_extra=AN_APPOINTMENT
    )
    number: _text(24, 1) | None = Field(
        None,
        validate_default=True,
        description="The appointment's number (APT-YYYYMMDD-NNNN), when the id is not known.",
    )

    @field_validator("number")
    @classmethod
    def _number(cls, value, info: ValidationInfo):
        return _named(value, info, "id", SAY_WHICH_APPOINTMENT)


class AppointmentIdIn(In):
    """An appointment by its id alone: the one a deleted appointment keeps (APPOINTMENT-F11), the same in a separate
    copy of the business and in the business."""

    id: UUID = Field(title=T_APPOINTMENT, description="The appointment's id.")


class HistoryIn(AppointmentRefIn):
    limit: int = Field(
        100, ge=1, le=100, description="How many lines to return (1 to 100)."
    )
    offset: int = Field(0, ge=0, description="How many lines to skip.")


class ForCustomerIn(CustomerOf):
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="How many appointments, the newest first (1 to 100).",
    )
    offset: int = Field(0, ge=0, description="How many to skip.")


class CountForServiceIn(ServiceRefIn):
    pass


class LineOut(Schema):
    service_id: UUID
    name: str = Field(description="The service's name when it was booked.")
    price: int = Field(description="Its price when it was booked, in cents.", json_schema_extra={"money": True})
    duration_minutes: int


class AppointmentRow(Schema):
    """An appointment as the agenda lists it: no contact and no notes."""

    id: UUID
    number: str
    customer_id: UUID
    customer_name: str = Field(description="Empty when the customer's data was erased.")
    staff_id: UUID | None = Field(
        description="Empty = unassigned (its professional left)."
    )
    staff_name: str
    start: dt.datetime = Field(description="On the business's clock.")
    end: dt.datetime
    duration_minutes: int
    status: Status
    source: Source
    services: list[LineOut]
    service_names: str = Field(description="The services' names, joined.")
    total: int = Field(description="The sum of its services' prices, in cents.", json_schema_extra={"money": True})
    booked_by_customer: bool
    sale_id: UUID | None = Field(
        description="The sale that charged it; empty = not charged."
    )
    order_id: UUID | None = Field(
        description="The check open in the till (Sales) to charge it; empty = none. Charging again goes back to it."
    )
    recurring_id: UUID | None
    occurrence_date: dt.date | None


class AppointmentOut(AppointmentRow):
    customer_phone: str | None = PHONE
    customer_email: str | None = EMAIL
    notes: str
    internal_notes: str
    cancelled_at: dt.datetime | None
    cancellation_reason: str
    cancelled_by_customer: bool
    charged_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    start_date_label: str = Field(
        description="Its day ready to say, in the caller's language on the business's clock (e.g. martes, 5 de "
        "marzo de 2030)."
    )
    start_time_label: str = Field(description="Its hour ready to say, 24-hour on the business's clock (e.g. 10:30).")
    label: str = Field(
        description="The words a card names it by, in the caller's language: its customer, day, hour and professional."
    )


class AppointmentsOut(Schema):
    rows: list[AppointmentOut]


class HistoryOut(Schema):
    id: UUID
    action: HistoryAction
    at: dt.datetime
    actor: str = Field(description="Who did it: a person's name, an API key's or the platform's own mark.")
    by_customer: bool
    by_platform: bool = Field(description="No person did it: the platform (the system, an automation, a recovery).")
    reason: str
    old_value: dict
    new_value: dict


class HistoryPage(Page[HistoryOut]):
    pass


class VisitOut(AppointmentRow):
    notes: str
    internal_notes: str


class VisitPage(Page[VisitOut]):
    pass


class CountOut(Schema):
    count: int
    earliest: dt.datetime | None = Field(
        description="The first one's start; empty when there is none."
    )


class NoticesIn(In):
    since: dt.datetime | None = Field(
        None, description="Only what happened from this instant on; empty = the last 24 hours."
    )
    limit: int = Field(20, ge=1, le=50, description="How many notices, the newest first (1 to 50).")


class NoticeOut(Schema):
    kind: Literal["booked", "cancelled"] = Field(
        description="booked: the customer booked it herself; cancelled: she cancelled it herself."
    )
    at: dt.datetime = Field(description="When she did it.")
    id: UUID
    number: str
    customer_name: str = Field(description="Empty once the customer's data was erased.")
    service_names: str
    staff_name: str
    start: dt.datetime
    start_date_label: str = Field(description="Its day ready to say, in the caller's language.")
    start_time_label: str = Field(description="Its hour ready to say, 24-hour on the business's clock.")


class NoticesOut(Schema):
    rows: list[NoticeOut] = Field(description="The notices, the newest first.")
