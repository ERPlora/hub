"""Schemas of the availability: a day with its blocks, opening hours and slots, and the tables free at a time."""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema

from apps.reservation.schemas.blocked_dates import BlockedDateOut
from apps.reservation.schemas.fields import Guests, In, Minutes


class DayIn(In):
    date: dt.date | None = Field(
        None, description="The day, YYYY-MM-DD; empty = the business's today."
    )



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
