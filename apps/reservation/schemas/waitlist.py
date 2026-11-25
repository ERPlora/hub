"""Schemas of the waitlist: its list, writing an entry down, naming, changing and converting it, and what the book
answers."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.customer.schemas.contact import EMAIL, PHONE
from apps.reservation.schemas.fields import (
    A_CUSTOMER,
    AN_ENTRY,
    D_GUEST_NAME,
    D_GUEST_PHONE,
    D_LABEL,
    GUEST,
    SAY_FOR_WHOM,
    Email,
    GuestName,
    Guests,
    In,
    Notes,
    Page,
    PageIn,
    Phone,
    Said,
)
from apps.reservation.schemas.reservations import ReservationOut
from base.sensitive import CUSTOMER_CONTACT

SAY_WHICH_ENTRY = _("Say which waitlist entry: its id, or its guest's name or phone.")

WaitlistSort = Literal[
    "position",
    "date",
    "-date",
    "preferred_time",
    "-preferred_time",
    "guest_name",
    "-guest_name",
    "party_size",
    "-party_size",
    "is_contacted",
    "-is_contacted",
]


class WaitlistListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the guest's name (or phone or email, for whoever sees them)."
    )
    date_from: dt.date | None = Field(None, description="From this day (included).")
    date_to: dt.date | None = Field(None, description="Until this day (included).")
    is_contacted: bool | None = Field(
        None, description="Only the contacted (true) or not contacted (false)."
    )
    is_converted: bool | None = Field(
        None, description="Only the converted (true) or still waiting (false)."
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
    sort: WaitlistSort = Field(
        "position",
        description="Order (position = day, preferred time and arrival); a leading '-' reverses it.",
    )


class WaitlistIn(In):
    customer_id: UUID | None = Field(
        None,
        description="The guest's customer card (an id of Customers).",
        json_schema_extra=A_CUSTOMER,
    )
    customer: Said | None = Field(
        None, description="The guest's customer card by name, phone or email."
    )
    guest_name: GuestName = Field("", description=D_GUEST_NAME)
    guest_phone: Phone = Field("", description=D_GUEST_PHONE)
    guest_email: Email = Field("", description="The guest's email.")
    date: dt.date = Field(description="The day they want, YYYY-MM-DD.")
    preferred_time: dt.time = Field(description="The time they would like, HH:MM.")
    party_size: Guests = Field(description="How many guests.")
    notes: Notes = Field("", description="Notes.")

    @model_validator(mode="after")
    def _for_whom(self):
        if not self.guest_name and self.customer_id is None and not self.customer:
            raise ValueError(str(SAY_FOR_WHOM))
        return self


class WaitlistRefIn(In):
    id: UUID | None = Field(
        None,
        title=gettext_noop("Waitlist entry"),
        description="The entry's id.",
        json_schema_extra=AN_ENTRY,
    )
    guest: Said | None = Field(
        None,
        title=GUEST,
        description="The guest's name (or phone, for whoever sees it), when the id is not known.",
    )
    day: dt.date | None = Field(
        None,
        title=gettext_noop("Date"),
        description="The entry's day, to tell it apart when the guest waits for several.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and not self.guest:
            raise ValueError(str(SAY_WHICH_ENTRY))
        return self


class WaitlistConvertIn(WaitlistRefIn):
    overbook: bool = Field(
        False,
        title=gettext_noop("Convert anyway"),
        description="True converts it into a slot already full, knowingly (after a reservation.no_capacity refusal).",
    )


class WaitlistPatchIn(WaitlistRefIn):
    is_contacted: bool | None = Field(
        None, description="True once the guest has been called."
    )
    notes: Notes | None = Field(None, description="New notes.")


class WaitlistOut(Schema):
    id: UUID = Field(description="The entry's id.")
    customer_id: UUID | None = Field(description="The guest's customer card.")
    guest_name: str = Field(
        description="The guest's name; empty once the customer's data was erased."
    )
    guest_phone: str | None = PHONE
    guest_email: str | None = EMAIL
    date: dt.date = Field(description="The day they want.")
    preferred_time: dt.time = Field(description="The time they would like.")
    party_size: int = Field(description="How many guests.")
    notes: str = Field(description="Notes.")
    is_contacted: bool = Field(description="True once the guest has been called.")
    contacted_at: dt.datetime | None = Field(description="When.")
    is_converted: bool = Field(description="True once it became a reservation.")
    reservation_id: UUID | None = Field(description="The reservation it became.")
    created_at: dt.datetime = Field(description="When it was written down.")


class WaitlistDetailOut(WaitlistOut):
    label: str = Field(
        description=D_LABEL.format(example="Luis Pérez · 15 oct 2026 · 21:00")
    )


class WaitlistPage(Page[WaitlistOut]):
    pass


class ConvertedOut(Schema):
    entry: WaitlistOut = Field(description="The entry, converted.")
    reservation: ReservationOut = Field(description="The reservation it became.")
