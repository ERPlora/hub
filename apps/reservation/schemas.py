"""Input and output schemas of the reservation app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is named
by its id or as a person says it (assistant, voice): a reservation by its guest's name or phone and its
day («Ana's reservation tomorrow»), a table by its number («5») and, when the number repeats, its zone, a
customer by their name or phone, a slot by its weekday and start, a waitlist entry by its guest. Every
input refuses a field it does not declare; an edit changes only the fields it sends. A reservation's day
and time are the business's wall clock (``2026-10-15``, ``21:00``).

The inputs of the reactions to Customers' events read only what they need from its payload and ignore the
rest, never refuse it.
"""

import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.reservation.models import MAX_GUESTS, MAX_MINUTES

T = TypeVar("T")

SAY_FOR_WHOM = _("Say who the reservation is for: a customer, or the guest's name.")
SAY_WHICH_RESERVATION = _(
    "Say which reservation: its id, or its guest's name or phone."
)
SAY_WHICH_SLOT = _("Say which slot: its id, or its day of the week and start time.")
SAY_WHICH_BLOCK = _("Say which blocked date: its id, or its date.")
SAY_WHICH_ENTRY = _("Say which waitlist entry: its id, or its guest's name or phone.")
SLOT_ENDS_BEFORE = _("A slot has to end after it starts.")
BLOCK_NEEDS_HOURS = _("Give the hours it blocks, or block the whole day.")
BLOCK_ENDS_BEFORE = _("The blocked hours have to end after they start.")

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
    "guest_phone",
    "-guest_phone",
    "party_size",
    "-party_size",
    "table",
    "-table",
    "status",
    "-status",
    "created_at",
    "-created_at",
]
SlotSort = Literal[
    "day_of_week",
    "-day_of_week",
    "start_time",
    "-start_time",
    "end_time",
    "-end_time",
    "max_reservations",
    "-max_reservations",
]
BlockedSort = Literal[
    "date", "-date", "reason", "-reason", "is_full_day", "-is_full_day"
]
WaitlistSort = Literal[
    "position",
    "date",
    "-date",
    "preferred_time",
    "-preferred_time",
    "guest_name",
    "-guest_name",
    "guest_phone",
    "-guest_phone",
    "party_size",
    "-party_size",
    "is_contacted",
    "-is_contacted",
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(100, 1)
GuestName = _text(200)
Phone = _text(60)
Email = _text(254)
Notes = _text(2000)
Guests = Annotated[int, Field(ge=1, le=MAX_GUESTS)]
Minutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]
Weekday = Annotated[int, Field(ge=0, le=6)]

D_GUEST_NAME = (
    "The guest's name as the staff say it at the door; empty takes the customer card's."
)
D_GUEST_PHONE = (
    "The guest's phone as typed; with no customer chosen, the live card with this number is used, or one "
    "is created."
)
D_TABLE_ID = "The table to book (an id of Tables)."
D_TABLE = "The table's number, e.g. «5», when its id is not known."
D_ZONE = "The table's zone, when the same number is in several zones."
D_OVERBOOK = (
    "True books a slot already full, knowingly: after a reservation.no_capacity refusal of a booking by phone or "
    "in person, ask and send it again with this. Never for online or WhatsApp bookings."
)


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, to read the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


class NoIn(In):
    pass


class DeletedOut(Schema):
    id: UUID = Field(description="The id of what was deleted.")


class ChangedOut(Schema):
    changed: int = Field(description="How many rows changed.")


# ── Reservations ─────────────────────────────────────────────────────────────────────────────────


class ReservationListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=100,
        description="Part of the guest's name, phone or email: searches the whole book, not only the days asked.",
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
    id: UUID | None = Field(None, description="The reservation's id.")
    guest: Said | None = Field(
        None,
        description="The guest's name or phone, when the id is not known («Ana», «600 111 222»).",
    )
    day: dt.date | None = Field(
        None,
        description="The reservation's day, YYYY-MM-DD, to tell it apart when the guest has several.",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and not self.guest:
            raise ValueError(str(SAY_WHICH_RESERVATION))
        return self


class ReservationIn(In):
    customer_id: UUID | None = Field(
        None, description="The guest's customer card (an id of Customers)."
    )
    customer: Said | None = Field(
        None,
        description="The guest's customer card by name, phone or email, when its id is not known.",
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
    table_id: UUID | None = Field(None, description=D_TABLE_ID)
    table: Said | None = Field(None, description=D_TABLE)
    zone: Said | None = Field(None, description=D_ZONE)
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
    overbook: bool = Field(False, description=D_OVERBOOK)

    @model_validator(mode="after")
    def _for_whom(self):
        if not self.guest_name and self.customer_id is None and not self.customer:
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
    table_id: UUID | None = Field(None, description="The new table (an id of Tables).")
    table: Said | None = Field(None, description="The new table's number, e.g. «5».")
    zone: Said | None = Field(None, description=D_ZONE)
    no_table: bool = Field(
        False, description="True leaves the reservation without a table."
    )
    notes: Notes | None = Field(None, description="The guest's new notes.")
    internal_notes: Notes | None = Field(
        None, description="The restaurant's new internal notes."
    )
    overbook: bool = Field(False, description=D_OVERBOOK)


class CancelIn(ReservationRefIn):
    reason: _text(500) = Field("", description="Why it is cancelled (optional).")


class ReservationOut(Schema):
    id: UUID = Field(description="The reservation's id.")
    customer_id: UUID | None = Field(description="The guest's customer card.")
    guest_name: str = Field(
        description="The guest's name; empty once the customer's data was erased."
    )
    guest_phone: str = Field(description="The guest's phone.")
    guest_email: str = Field(description="The guest's email.")
    date: dt.date = Field(description="The day.")
    time: dt.time = Field(description="The time, on the business's clock.")
    end_time: dt.time = Field(
        description="When the table is free again, on the business's clock."
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


class ReservationPage(Page[ReservationOut]):
    pass


class ReleasedOut(Schema):
    released: int = Field(
        description="How many unconfirmed reservations were released."
    )


# ── Availability ─────────────────────────────────────────────────────────────────────────────────


class DayIn(In):
    date: dt.date | None = Field(
        None, description="The day, YYYY-MM-DD; empty = the business's today."
    )


class BlockedDateOut(Schema):
    id: UUID = Field(description="The blocked date's id.")
    date: dt.date = Field(description="The day blocked.")
    reason: str = Field(description="Why (holiday, closure, private event).")
    is_full_day: bool = Field(description="True when the whole day is blocked.")
    blocked_from: dt.time | None = Field(
        description="From what time, when only some hours are blocked."
    )
    blocked_until: dt.time | None = Field(description="Until what time (included).")


class SpanOut(Schema):
    start: dt.datetime = Field(description="The business opens (wall clock, no zone).")
    end: dt.datetime = Field(description="The business closes (wall clock, no zone).")


class SlotLoadOut(Schema):
    id: UUID = Field(description="The slot's id.")
    start_time: dt.time = Field(description="The slot starts.")
    end_time: dt.time = Field(description="The slot ends (excluded).")
    max_reservations: int = Field(description="How many reservations fit.")
    max_covers: int | None = Field(
        description="How many guests fit; empty = not limited."
    )
    reserved: int = Field(
        description="Live reservations in it (not cancelled nor no-show)."
    )
    covers: int = Field(description="Their guests.")
    available: int = Field(description="Reservations left.")
    full: bool = Field(description="True when nothing more fits.")
    in_hours: bool = Field(
        description="False when the slot starts with the business closed (Schedules)."
    )


class DayOut(Schema):
    date: dt.date = Field(description="The day.")
    today: dt.date = Field(description="The business's today.")
    timezone: str = Field(description="The business's time zone.")
    closed: bool = Field(description="True when the whole day is blocked.")
    blocks: list[BlockedDateOut] = Field(description="The day's blocks.")
    hours_restricted: bool = Field(description="True when Schedules governs the day.")
    spans: list[SpanOut] = Field(
        description="The day's opening spans (empty and restricted = closed)."
    )
    slots: list[SlotLoadOut] = Field(
        description="The day's slots, by start, with what they hold."
    )
    reservations: int = Field(
        description="The day's live reservations (not cancelled nor no-show)."
    )
    covers: int = Field(description="Their guests: the day's covers.")


class TablesIn(In):
    date: dt.date = Field(description="The day, YYYY-MM-DD.")
    time: dt.time = Field(description="The time, HH:MM.")
    duration_minutes: Minutes | None = Field(
        None, description="How long, in minutes; empty = the book's default."
    )
    party_size: Guests | None = Field(
        None, description="How many guests: the tables that fit them come first."
    )
    exclude_id: UUID | None = Field(
        None,
        description="A reservation being changed, which does not count against its table.",
    )
    search: str | None = Field(
        None, max_length=100, description="Part of the table's number, name or zone."
    )


class FreeTableOut(Schema):
    id: UUID = Field(description="The table's id.")
    number: str = Field(description="Its number.")
    label: str = Field(description="As it is read: «5 (Terrace)».")
    zone_name: str = Field(description="Its zone.")
    capacity: int = Field(description="Its seats.")
    fits: bool = Field(description="True when the party fits its seats.")
    free: bool = Field(
        description="True when no live reservation holds it at that time."
    )
    taken_from: dt.time | None = Field(
        description="When the reservation that holds it starts."
    )
    taken_until: dt.time | None = Field(description="When it ends.")


class FreeTablesOut(Schema):
    rows: list[FreeTableOut] = Field(
        description="The tables in service: free and fitting first, then by number."
    )


# ── Slots and blocked dates ──────────────────────────────────────────────────────────────────────


class TimeSlotListIn(PageIn):
    day_of_week: Weekday | None = Field(
        None, description="Only the slots of this weekday (0 = Monday … 6 = Sunday)."
    )
    sort: SlotSort = Field(
        "day_of_week", description="Order; a leading '-' reverses it."
    )


class TimeSlotIn(In):
    day_of_week: Weekday = Field(description="The weekday: 0 = Monday … 6 = Sunday.")
    start_time: dt.time = Field(description="From, HH:MM.")
    end_time: dt.time = Field(description="To, HH:MM (excluded), the same day.")
    max_reservations: int = Field(
        10, ge=1, le=MAX_GUESTS, description="How many reservations fit in it."
    )
    max_covers: int | None = Field(
        None,
        ge=1,
        le=9999,
        description="How many guests fit in it; empty = only the reservations count.",
    )

    @field_validator("end_time")
    @classmethod
    def _ends_after(cls, value: dt.time, info: ValidationInfo) -> dt.time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError(str(SLOT_ENDS_BEFORE))
        return value


class TimeSlotRefIn(In):
    id: UUID | None = Field(None, description="The slot's id.")
    day_of_week: Weekday | None = Field(
        None, description="Its weekday, when the id is not known."
    )
    start_time: dt.time | None = Field(
        None, description="Its start, HH:MM, with its weekday."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and (self.day_of_week is None or self.start_time is None):
            raise ValueError(str(SAY_WHICH_SLOT))
        return self


class TimeSlotOut(Schema):
    id: UUID = Field(description="The slot's id.")
    day_of_week: int = Field(description="0 = Monday … 6 = Sunday.")
    start_time: dt.time = Field(description="From.")
    end_time: dt.time = Field(description="To (excluded).")
    max_reservations: int = Field(description="How many reservations fit.")
    max_covers: int | None = Field(
        description="How many guests fit; empty = not limited."
    )


class TimeSlotPage(Page[TimeSlotOut]):
    pass


class BlockedDateListIn(PageIn):
    date_from: dt.date | None = Field(None, description="From this day (included).")
    date_to: dt.date | None = Field(None, description="Until this day (included).")
    is_full_day: bool | None = Field(
        None, description="Only whole days (true) or only some hours (false)."
    )
    sort: BlockedSort = Field("date", description="Order; a leading '-' reverses it.")


class BlockedDateIn(In):
    date: dt.date = Field(description="The day, YYYY-MM-DD.")
    reason: _text(200) = Field(
        "", description="Why: a holiday, a closure, a private event."
    )
    is_full_day: bool = Field(
        True, description="True blocks the whole day; false, only the hours given."
    )
    blocked_from: dt.time | None = Field(
        None,
        validate_default=True,
        description="From, HH:MM, when only some hours are blocked.",
    )
    blocked_until: dt.time | None = Field(
        None,
        validate_default=True,
        description="Until, HH:MM (included), when only some hours are blocked.",
    )

    @field_validator("blocked_from")
    @classmethod
    def _from_given(cls, value: dt.time | None, info: ValidationInfo) -> dt.time | None:
        if info.data.get("is_full_day") is False and value is None:
            raise ValueError(str(BLOCK_NEEDS_HOURS))
        return value

    @field_validator("blocked_until")
    @classmethod
    def _until_after(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if info.data.get("is_full_day") is not False:
            return value
        if value is None:
            raise ValueError(str(BLOCK_NEEDS_HOURS))
        start = info.data.get("blocked_from")
        if start is not None and value <= start:
            raise ValueError(str(BLOCK_ENDS_BEFORE))
        return value


class BlockedDateRefIn(In):
    id: UUID | None = Field(None, description="The blocked date's id.")
    date: dt.date | None = Field(
        None, description="Its day, YYYY-MM-DD, when the id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.date is None:
            raise ValueError(str(SAY_WHICH_BLOCK))
        return self


class BlockedDatePage(Page[BlockedDateOut]):
    pass


# ── Waitlist ─────────────────────────────────────────────────────────────────────────────────────


class WaitlistListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the guest's name, phone or email."
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
    )
    sort: WaitlistSort = Field(
        "position",
        description="Order (position = day, preferred time and arrival); a leading '-' reverses it.",
    )


class WaitlistIn(In):
    customer_id: UUID | None = Field(
        None, description="The guest's customer card (an id of Customers)."
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
    id: UUID | None = Field(None, description="The entry's id.")
    guest: Said | None = Field(
        None, description="The guest's name or phone, when the id is not known."
    )
    day: dt.date | None = Field(
        None,
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
    guest_phone: str = Field(description="The guest's phone.")
    guest_email: str = Field(description="The guest's email.")
    date: dt.date = Field(description="The day they want.")
    preferred_time: dt.time = Field(description="The time they would like.")
    party_size: int = Field(description="How many guests.")
    notes: str = Field(description="Notes.")
    is_contacted: bool = Field(description="True once the guest has been called.")
    contacted_at: dt.datetime | None = Field(description="When.")
    is_converted: bool = Field(description="True once it became a reservation.")
    reservation_id: UUID | None = Field(description="The reservation it became.")
    created_at: dt.datetime = Field(description="When it was written down.")


class WaitlistPage(Page[WaitlistOut]):
    pass


class ConvertedOut(Schema):
    entry: WaitlistOut = Field(description="The entry, converted.")
    reservation: ReservationOut = Field(description="The reservation it became.")


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


class SettingsIn(In):
    min_party_size: Guests | None = Field(
        None, description="The fewest guests a reservation takes."
    )
    max_party_size: Guests | None = Field(
        None, description="The most guests a reservation takes."
    )
    min_advance_hours: int | None = Field(
        None,
        ge=0,
        le=720,
        description="Hours of notice a guest booking herself (online, WhatsApp) must give.",
    )
    max_advance_days: int | None = Field(
        None, ge=0, le=365, description="How many days ahead a guest booking herself (online, WhatsApp) may book; the staff are not bound."
    )
    default_duration_minutes: Minutes | None = Field(
        None, description="How long a reservation keeps its table."
    )
    auto_confirm: bool | None = Field(
        None, description="True: every new reservation is born confirmed."
    )
    require_phone: bool | None = Field(
        None, description="True: every reservation needs a phone."
    )
    require_email: bool | None = Field(
        None, description="True: every reservation needs an email."
    )
    no_show_window_minutes: int | None = Field(
        None,
        ge=0,
        le=1440,
        description="Minutes after its time an unconfirmed reservation is released.",
    )


class SettingsOut(Schema):
    min_party_size: int = Field(description="The fewest guests a reservation takes.")
    max_party_size: int = Field(description="The most guests a reservation takes.")
    min_advance_hours: int = Field(
        description="Hours of notice for the guest booking herself."
    )
    max_advance_days: int = Field(description="How many days ahead a guest booking herself (online, WhatsApp) may book; the staff are not bound.")
    default_duration_minutes: int = Field(
        description="How long a reservation keeps its table."
    )
    auto_confirm: bool = Field(description="Every new reservation is born confirmed.")
    require_phone: bool = Field(description="Every reservation needs a phone.")
    require_email: bool = Field(description="Every reservation needs an email.")
    no_show_window_minutes: int = Field(
        description="Minutes after its time an unconfirmed reservation is released."
    )
    timezone: str = Field(
        description="The business's time zone (phase 1: Europe/Madrid)."
    )


# ── Reactions to Customers ───────────────────────────────────────────────────────────────────────


class MergedIn(Reaction):
    """``customer.customer.merged``: the card that stays and the one absorbed."""

    id: UUID | None = Field(None, description="The card that stays.")
    absorbed_id: UUID | None = Field(None, description="The card merged into it.")


class CustomerEventIn(Reaction):
    """``customer.customer.erased``: the card whose personal data was erased."""

    id: UUID | None = Field(None, description="The erased customer's card.")
