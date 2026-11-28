"""The public page: what it shows, the services and free times it offers, the booking a customer makes there and her
personal link."""

import datetime as dt
from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import field_validator

from apps.appointment.schemas.fields import A_MEMBER, A_SERVICE, OF_STATUS
from apps.customer.schemas.fields import Email
from apps.online_booking.public_page import LinkOwnerOut, PageOwnerOut, TrapIn
from apps.online_booking.schemas.fields import In, Page, Status, _text
from apps.online_booking.service_price import ServicePriceOut

#: Services in one booking made on the page.
MAX_SERVICES = 5

SAME_SERVICE_TWICE = _("Each service only once.")


class PageOut(PageOwnerOut):
    title: str = Field(description="The page's own title, or «Book an appointment» in the visitor's language.")
    welcome_message: str
    primary_color: str
    require_email: bool
    allow_staff_selection: bool
    allow_notes: bool
    cancellation_policy: str
    min_booking_notice: int = Field(description="Minutes ahead she must book.")
    max_advance_booking: int = Field(
        description="Days ahead she may book; 0 = no limit."
    )
    allow_customer_cancellation: bool
    cancellation_notice_hours: int
    timezone: str


class PublicServicesIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many services to return (1 to 100)."
    )
    offset: int = Field(0, ge=0, description="How many to skip.")
    search: _text(100) = Field(
        "", description="Part of the service's or its category's name."
    )


class ProfessionalOut(Schema):
    id: UUID
    name: str


class PublicServiceOut(ServicePriceOut):
    id: UUID
    name: str
    description: str
    category: str = Field(description="Its category's name; empty without one.")
    duration_minutes: int | None = Field(
        description="Empty when the business does not show durations."
    )
    professionals: list[ProfessionalOut] = Field(
        description="Who may do it; empty when the business does not let the customer choose."
    )


class PublicServicePage(Page[PublicServiceOut]):
    pass


#: Each service by its name on the card.
ServiceIds = Annotated[
    list[Annotated[UUID, Field(json_schema_extra=A_SERVICE)]],
    Field(min_length=1, max_length=MAX_SERVICES),
]


def _different(value: list[UUID]) -> list[UUID]:
    if len(set(value)) != len(value):
        raise ValueError(str(SAME_SERVICE_TWICE))
    return value


class PublicSlotsIn(In):
    service_ids: ServiceIds = Field(
        description="The services to book (1 to 5), in order."
    )
    date: dt.date = Field(description="The business day (YYYY-MM-DD).")
    staff_id: UUID | None = Field(
        None, description="The professional chosen; empty = anybody who does them."
    )

    _different = field_validator("service_ids")(lambda cls, value: _different(value))


class PublicSlotOut(Schema):
    start: dt.datetime
    end: dt.datetime
    professionals: list[ProfessionalOut] = Field(
        description="Who is free then; empty when the business does not let the customer choose."
    )


class PublicSlotsOut(Schema):
    date: dt.date
    timezone: str
    duration_minutes: int
    slots: list[PublicSlotOut]


class PublicBookIn(In, TrapIn):
    service_ids: ServiceIds = Field(
        title=gettext_noop("Services"),
        description="The services to book (1 to 5), in order.",
    )
    staff_id: UUID | None = Field(
        None,
        title=gettext_noop("Professional"),
        description="The professional chosen; empty = anybody free then.",
        json_schema_extra=A_MEMBER,
    )
    start: dt.datetime = Field(
        title=gettext_noop("Day and time"),
        description="When it starts: the business's wall-clock date and time (2030-03-05 10:00).",
    )
    name: _text(200, 1) = Field(description="The customer's full name.")
    phone: _text(30, 1) = Field(
        description="Her mobile, as typed; saved in international format."
    )
    email: Email = Field(
        "", description="Her email (required when the business asks for it)."
    )
    notes: _text(500) = Field(
        "", description="A note for the business (when it allows notes)."
    )

    _different = field_validator("service_ids")(lambda cls, value: _different(value))


class BookedOut(Schema):
    number: str = Field(description="The appointment number the customer quotes.")
    status: Status = Field(json_schema_extra=OF_STATUS)
    start: dt.datetime
    end: dt.datetime
    timezone: str
    service_names: str
    staff_name: str
    message: str = Field(description="What the customer reads now.")
    token: str = Field(
        description="The customer's personal link token: shown once, never stored in clear."
    )


class TokenIn(In):
    token: _text(100, 20) = Field(
        title=gettext_noop("Personal link"),
        description="The token of the customer's personal link.",
    )


class PublicCancelIn(TokenIn):
    reason: _text(500) = Field("", description="Why she cancels (optional).")


class PublicBookingOut(LinkOwnerOut):
    number: str
    status: Status = Field(json_schema_extra=OF_STATUS)
    start: dt.datetime
    end: dt.datetime
    timezone: str
    service_names: str
    staff_name: str
    can_cancel: bool = Field(description="She may still cancel it from the link.")
    cancel_until: dt.datetime | None = Field(
        description="Until when she may cancel it; empty = she may not."
    )
    cancellation_policy: str
