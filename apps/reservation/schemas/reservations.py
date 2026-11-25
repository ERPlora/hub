"""Schemas of the reservations: the book's list, naming one, taking, changing and cancelling it, and what the book
answers."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.customer.schemas.contact import EMAIL, PHONE
from apps.customer.schemas.fields import A_CUSTOMER_SAID
from apps.reservation.schemas.fields import (
    A_CUSTOMER,
    A_RESERVATION,
    A_TABLE,
    BOOK_ANYWAY,
    D_GUEST_NAME,
    D_GUEST_PHONE,
    D_LABEL,
    GUEST,
    ON_BEHALF_OF,
    SAY_FOR_WHOM,
    ZONE,
    Email,
    GuestName,
    Guests,
    In,
    Minutes,
    Notes,
    Page,
    PageIn,
    Phone,
    Said,
    _text,
)
from base.schemas.assistant import unless_given
from base.sensitive import CUSTOMER_CONTACT

#: The sources where the guest books herself (engine.GUEST_SOURCES): without a name, her phone names her.
GUEST_BOOKS = frozenset({"online", "whatsapp"})
D_ON_BEHALF_OF = (
    "Only for a channel acting for the guest herself (WhatsApp): her customer card. The reservation must be hers; "
    "the table, the internal notes and booking anyway stay the restaurant's, and her own booking rules apply."
)
SAY_WHICH_RESERVATION = _(
    "Say which reservation: its id, or its guest's name or phone."
)

Status = Literal["pending", "confirmed", "seated", "completed", "cancelled", "no_show"]
Source = Literal["phone", "in_person", "waitlist", "whatsapp", "online"]
#: Where a booking may come from when it is taken (the waitlist one is a conversion's).
BookingSource = Literal["phone", "in_person", "whatsapp", "online"]
ReservationSort = Literal[
    "starts_at",
    "-starts_at",
    "time",
    "-time",
    "guest_name",
    "-guest_name",
    "party_size",
    "-party_size",
    "table",
    "-table",
    "status",
    "-status",
    "created_at",
    "-created_at",
]

D_TABLE_ID = "The table to book (an id of Tables)."
D_TABLE = "The table's number, e.g. «5», when its id is not known."
D_ZONE = "The table's zone, when the same number is in several zones."
D_OVERBOOK = (
    "True books a slot already full, knowingly: after a reservation.no_capacity refusal of a booking by phone or "
    "in person, ask and send it again with this. Never for online or WhatsApp bookings."
)


class ReservationListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=100,
        description="Part of the guest's name (or phone or email, for whoever sees them): searches the whole book.",
    )
    date_from: dt.date | None = Field(
        None, description="First day, YYYY-MM-DD (included)."
    )
    date_to: dt.date | None = Field(
        None, description="Last day, YYYY-MM-DD (included)."
    )
    status: Status | None = Field(
        None, description="Only the reservations in this status."
    )
    table_id: UUID | None = Field(
        None, description="Only the reservations of this table."
    )
    customer_id: UUID | None = Field(
        None, description="Only the reservations of this customer's card."
    )
    guest_name: str | None = Field(
        None,
        max_length=100,
        description="Part of the guest's name (the column filter).",
    )
    guest_phone: str | None = Field(
        None,
        max_length=60,
        description="Part of the guest's phone (the column filter).",
        json_schema_extra=CUSTOMER_CONTACT,
    )
    time: str | None = Field(
        None,
        max_length=5,
        description="Part of the time, e.g. «21» (the column filter).",
    )
    party_size_from: int | None = Field(
        None, ge=1, description="At least this many guests."
    )
    party_size_to: int | None = Field(
        None, ge=1, description="At most this many guests."
    )
    sort: ReservationSort = Field(
        "starts_at",
        description="Order (starts_at = day and time); a leading '-' reverses it.",
    )


class ReservationRefIn(In):
    id: UUID | None = Field(
        None,
        title=gettext_noop("Reservation"),
        description="The reservation's id.",
        json_schema_extra=A_RESERVATION,
    )
    guest: Said | None = Field(
        None,
        title=GUEST,
        description="The guest's name (or phone, for whoever sees it), when the id is not known («Ana», «600 111 222»).",
    )
    day: dt.date | None = Field(
        None,
        title=gettext_noop("Reservation date"),
        description="The reservation's day, YYYY-MM-DD, to tell it apart when the guest has several.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and not self.guest:
            raise ValueError(str(SAY_WHICH_RESERVATION))
        return self


class ReservationIn(In):
    customer_id: UUID | None = Field(
        None,
        description="The guest's customer card (an id of Customers).",
        json_schema_extra=A_CUSTOMER,
    )
    customer: Said | None = Field(
        None,
        description="The guest's customer card by name, phone or email, when its id is not known.",
        json_schema_extra=unless_given(A_CUSTOMER_SAID, "customer_id"),
    )
    guest_name: GuestName = Field("", description=D_GUEST_NAME)
    guest_phone: Phone = Field("", description=D_GUEST_PHONE)
    guest_email: Email = Field("", description="The guest's email.")
    date: dt.date = Field(description="The day, YYYY-MM-DD on the business's calendar.")
    time: dt.time = Field(description="The time, HH:MM on the business's clock.")
    party_size: Guests = Field(description="How many guests come.")
    duration_minutes: Minutes | None = Field(
        None,
        description="How long the table is kept, in minutes; empty = the book's default (120).",
    )
    table_id: UUID | None = Field(
        None, description=D_TABLE_ID, json_schema_extra=A_TABLE
    )
    table: Said | None = Field(None, description=D_TABLE)
    zone: Said | None = Field(None, title=ZONE, description=D_ZONE)
    source: BookingSource = Field(
        "phone",
        description="How it was booked: phone, in_person, whatsapp or online (the last two keep the minimum notice).",
    )
    notes: Notes = Field(
        "", description="The guest's notes (an occasion, a high chair)."
    )
    internal_notes: Notes = Field(
        "", description="The restaurant's own notes, never shown to the guest."
    )
    overbook: bool = Field(False, title=BOOK_ANYWAY, description=D_OVERBOOK)

    @model_validator(mode="after")
    def _for_whom(self):
        named = self.guest_name or self.customer_id is not None or self.customer
        # A guest who books herself without a name (a WhatsApp message) is booked under her phone.
        if not named and not (self.source in GUEST_BOOKS and self.guest_phone):
            raise ValueError(str(SAY_FOR_WHOM))
        return self


class ReservationPatchIn(ReservationRefIn):
    guest_name: GuestName | None = Field(None, description="The guest's new name.")
    guest_phone: Phone | None = Field(None, description="The guest's new phone.")
    guest_email: Email | None = Field(None, description="The guest's new email.")
    date: dt.date | None = Field(None, description="The new day, YYYY-MM-DD.")
    time: dt.time | None = Field(None, description="The new time, HH:MM.")
    party_size: Guests | None = Field(None, description="The new number of guests.")
    duration_minutes: Minutes | None = Field(
        None, description="The new duration, in minutes."
    )
    table_id: UUID | None = Field(
        None, description="The new table (an id of Tables).", json_schema_extra=A_TABLE
    )
    table: Said | None = Field(None, description="The new table's number, e.g. «5».")
    zone: Said | None = Field(None, title=ZONE, description=D_ZONE)
    no_table: bool = Field(
        False,
        title=gettext_noop("No table"),
        description="True leaves the reservation without a table.",
    )
    notes: Notes | None = Field(None, description="The guest's new notes.")
    internal_notes: Notes | None = Field(
        None, description="The restaurant's new internal notes."
    )
    overbook: bool = Field(False, title=BOOK_ANYWAY, description=D_OVERBOOK)
    on_behalf_of: UUID | None = Field(
        None,
        title=ON_BEHALF_OF,
        description=D_ON_BEHALF_OF,
        json_schema_extra=A_CUSTOMER,
    )


class CancelIn(ReservationRefIn):
    reason: _text(500) = Field("", description="Why it is cancelled (optional).")
    on_behalf_of: UUID | None = Field(
        None,
        title=ON_BEHALF_OF,
        description=D_ON_BEHALF_OF,
        json_schema_extra=A_CUSTOMER,
    )


class ReservationOut(Schema):
    id: UUID = Field(description="The reservation's id.")
    customer_id: UUID | None = Field(description="The guest's customer card.")
    guest_name: str = Field(
        description="The guest's name; empty once the customer's data was erased."
    )
    guest_phone: str | None = PHONE
    guest_email: str | None = EMAIL
    date: dt.date = Field(description="The day.")
    time: dt.time = Field(description="The time, on the business's clock.")
    end_time: dt.time = Field(
        description="When the table is free again, on the business's clock."
    )
    date_label: str = Field(
        description="Its day ready to say, in the caller's language (e.g. martes, 5 de marzo de 2030)."
    )
    time_label: str = Field(
        description="Its hour ready to say, 24-hour on the business's clock (e.g. 21:30)."
    )
    duration_minutes: int = Field(description="How long the table is kept, in minutes.")
    party_size: int = Field(description="How many guests come.")
    table_id: UUID | None = Field(description="The table, if it has one.")
    table_label: str = Field(
        description="The table as it is read: «5 (Terrace)»; empty without one."
    )
    table_capacity: int | None = Field(description="The table's seats.")
    status: Status = Field(
        description="pending, confirmed, seated, completed, cancelled or no_show."
    )
    source: Source = Field(description="How it was booked.")
    notes: str = Field(description="The guest's notes.")
    internal_notes: str = Field(description="The restaurant's internal notes.")
    cancellation_reason: str = Field(
        description="Why it was cancelled («unconfirmed» = released unconfirmed)."
    )
    confirmed_at: dt.datetime | None = Field(description="When it was confirmed.")
    seated_at: dt.datetime | None = Field(description="When it was seated.")
    completed_at: dt.datetime | None = Field(description="When it was completed.")
    cancelled_at: dt.datetime | None = Field(description="When it was cancelled.")
    no_show_at: dt.datetime | None = Field(description="When it was marked a no-show.")
    table_session_id: UUID | None = Field(
        description="The check of Tables that seating it opened."
    )
    waitlist_entry_id: UUID | None = Field(
        description="The waitlist entry it was converted from."
    )
    created_at: dt.datetime = Field(description="When it was taken.")
    updated_at: dt.datetime = Field(description="When it last changed.")


class ReservationDetailOut(ReservationOut):
    label: str = Field(
        description=D_LABEL.format(example="Ana García · 15 oct 2026 · 21:00")
    )


class ReservationPage(Page[ReservationOut]):
    pass


class ReleasedOut(Schema):
    released: int = Field(
        description="How many unconfirmed reservations were released."
    )
