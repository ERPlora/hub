"""Input and output schemas of the online booking app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every input field says what it is. A booking is
named by its id, its appointment number (``APT-…``) or as a person says it: the customer (name, phone or
email) and the day. A time without a zone is a wall-clock time of the business («2030-03-05 10:00»). Money is
in cents. Every input refuses a field it does not declare; the settings change only what they send.
"""

import datetime as dt
import re
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.customer.schemas import Email

T = TypeVar("T")

#: Services in one booking made on the page.
MAX_SERVICES = 5
#: The page's own texts.
MAX_TEXT = 2000

SAY_WHICH_BOOKING = _(
    "Say which booking: its number, or the customer's name, phone or email (and the day)."
)
END_BEFORE_START = _("The end cannot be before the start.")
NOT_A_COLOUR = _("Write the colour as #RRGGBB (for example #6366f1).")
NOT_AN_ADDRESS = _("Write a web address that starts with http:// or https://.")
SAME_SERVICE_TWICE = _("Each service only once.")

Status = Literal[
    "pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"
]
BookingSort = Literal[
    "booked_at", "start", "number", "customer_name", "staff_name", "status"
]
Dir = Literal["asc", "desc"]

_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _colour(value: str) -> str:
    if not _COLOUR.match(value):
        raise ValueError(str(NOT_A_COLOUR))
    return value


def _address(value: str) -> str:
    if value and not re.match(r"^https?://[^\s]+$", value):
        raise ValueError(str(NOT_AN_ADDRESS))
    return value


Colour = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=7), AfterValidator(_colour)
]
Address = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500),
    AfterValidator(_address),
]
Text = _text(MAX_TEXT)


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class NoIn(In):
    pass


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


# ── The inbox ──────────────────────────────────────────────────────────────────────────────────


class BookingListIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )
    search: _text(100) = Field(
        "",
        description="Text in the number, the customer's name, phone or email, a service or the professional.",
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
        None, description="The booking's id (its appointment's id)."
    )
    number: _text(24, 1) | None = Field(
        None, description="The appointment number (APT-YYYYMMDD-NNNN)."
    )
    customer: _text(200, 1) | None = Field(
        None,
        description="The customer as a person says it: her name (or part of it), her phone or her email.",
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
    price: int = Field(description="Its price when it was booked, in cents.")
    duration_minutes: int


class BookingRow(Schema):
    """An online booking as the inbox lists it: the appointment and how to reach the customer."""

    id: UUID = Field(description="The appointment's id.")
    number: str
    customer_id: UUID
    customer_name: str = Field(description="Empty when the customer's data was erased.")
    customer_phone: str
    customer_email: str
    staff_id: UUID | None
    staff_name: str
    services: list[LineOut]
    service_names: str
    start: dt.datetime = Field(description="On the business's clock.")
    end: dt.datetime
    duration_minutes: int
    status: Status
    total: int = Field(description="The sum of its services' prices, in cents.")
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


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


class SettingsIn(In):
    """Only what is sent changes, all of it or nothing; the rules are the diary's (Citas)."""

    is_enabled: bool | None = Field(None, description="The public page takes bookings.")
    page_title: _text(120) | None = Field(
        None, description="The page's title; empty = «Book an appointment»."
    )
    welcome_message: Text | None = Field(
        None, description="The text at the top of the page."
    )
    primary_color: Colour | None = Field(
        None, description="The page's colour, as #RRGGBB."
    )
    logo_url: Address | None = Field(
        None, description="The address (http/https) of the business's logo."
    )
    require_email: bool | None = Field(
        None, description="The customer must leave her email."
    )
    max_upcoming_per_customer: int | None = Field(
        None,
        ge=1,
        le=50,
        description="How many upcoming online bookings one mobile may hold at once (1 to 50).",
    )
    allow_staff_selection: bool | None = Field(
        None, description="The customer may choose the professional."
    )
    allow_notes: bool | None = Field(None, description="The customer may leave a note.")
    confirmation_message: Text | None = Field(
        None,
        description="What the customer reads once she has booked; empty = the page's own.",
    )
    cancellation_policy: Text | None = Field(
        None, description="The cancellation policy the customer reads."
    )
    min_booking_notice: int | None = Field(
        None,
        ge=0,
        le=10080,
        description="Diary rule: minutes ahead the customer must book.",
    )
    max_advance_booking: int | None = Field(
        None,
        ge=0,
        le=365,
        description="Diary rule: days ahead one may book; 0 = no limit.",
    )
    slot_interval: int | None = Field(
        None, ge=5, le=240, description="Diary rule: minutes between free times."
    )
    auto_confirm_online: bool | None = Field(
        None,
        description="Diary rule: the customer's bookings are born confirmed (false: pending, to review).",
    )
    allow_customer_cancellation: bool | None = Field(
        None, description="Diary rule: the customer may cancel her booking."
    )
    cancellation_notice_hours: int | None = Field(
        None,
        ge=0,
        le=720,
        description="Diary rule: hours before the start she may still cancel.",
    )


class SettingsOut(Schema):
    is_enabled: bool
    page_title: str
    welcome_message: str
    primary_color: str
    logo_url: str
    require_email: bool
    max_upcoming_per_customer: int
    allow_staff_selection: bool
    allow_notes: bool
    confirmation_message: str
    cancellation_policy: str
    min_booking_notice: int
    max_advance_booking: int
    slot_interval: int
    auto_confirm_online: bool
    allow_customer_cancellation: bool
    cancellation_notice_hours: int
    timezone: str


# ── The public page ────────────────────────────────────────────────────────────────────────────


class PageOut(Schema):
    title: str = Field(
        description="The page's title (the business's, or the page's own)."
    )
    welcome_message: str
    primary_color: str
    logo_url: str
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


class PublicServiceOut(Schema):
    id: UUID
    name: str
    description: str
    category: str = Field(description="Its category's name; empty without one.")
    price: int | None = Field(
        description="In cents; empty when the business does not show prices."
    )
    duration_minutes: int | None = Field(
        description="Empty when the business does not show durations."
    )
    professionals: list[ProfessionalOut] = Field(
        description="Who may do it; empty when the business does not let the customer choose."
    )


class PublicServicePage(Page[PublicServiceOut]):
    pass


ServiceIds = Annotated[list[UUID], Field(min_length=1, max_length=MAX_SERVICES)]


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


class PublicBookIn(In):
    service_ids: ServiceIds = Field(
        description="The services to book (1 to 5), in order."
    )
    staff_id: UUID | None = Field(
        None, description="The professional chosen; empty = anybody free then."
    )
    start: dt.datetime = Field(
        description="When it starts: the business's wall-clock date and time (2030-03-05 10:00)."
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
    status: Status
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
        description="The token of the customer's personal link."
    )


class PublicCancelIn(TokenIn):
    reason: _text(500) = Field("", description="Why she cancels (optional).")


class PublicBookingOut(Schema):
    number: str
    status: Status
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


# ── Reactions to other apps' events (their payloads) ───────────────────────────────────────────


class Payload(Schema):
    """Another app's event payload: what this app reads of it (the rest is ignored)."""

    model_config = ConfigDict(extra="ignore")


class CustomerEventIn(Payload):
    id: UUID = Field(description="The customer's card.")


class ReactionOut(Schema):
    changed: int = Field(description="How many rows the reaction changed.")
