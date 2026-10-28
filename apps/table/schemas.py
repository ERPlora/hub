"""Input and output schemas of the table app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is
named by its id or, as a person says it (assistant, voice), by its number or its name: a table by its
number («4») and, when the number repeats, its zone («the terrace»); a zone by its name; a customer by
their name or phone. Every input refuses a field it does not declare; an edit changes only the fields
it sends. Moments travel ISO 8601 with their zone; money in cents.

The inputs of the reactions to other apps' events (Sales, Customers, Reservations) read only what they
need from the emitter's payload and ignore the rest, never refuse it.
"""

import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

from apps.table.models import (
    BOX,
    MAX_CAPACITY,
    MAX_MINUTES,
    MAX_PLAN,
    MIN_BOX,
    MIN_MINUTES,
)

T = TypeVar("T")

#: The most tables one bulk create makes (the old module's 100).
MAX_BULK = 100
#: A party may exceed the table's seats (it only warns); this is just a sanity cap.
MAX_GUESTS = 999
#: The lines of a check that move to the new one when it is split (Sales' own cap).
MAX_LINES = 500

SAY_WHICH_ZONE = _("Say which zone: its id, or its name.")
SAY_WHICH_TABLE = _("Say which table: its id, or its number.")
SAY_WHICH_CHECK = _("Say which check: its id, or the number of its table.")
SAY_WHERE_TO = _("Say which table it goes to: its id, or its number.")
SAY_WHICH_TARGET = _(
    "Say which table or check it joins: an id, or the number of its table."
)
HOLD_ENDS_BEFORE = _("A hold has to end after it starts.")
MOMENT_WITHOUT_ZONE = _("Give the moment with its time zone.")

# How the Tables screens name the data the models do not (the assistant's card names each datum by its title).
ZONE_COLOUR = gettext_noop("Zone colour")
DESTINATION_TABLE = gettext_noop("Destination table")
DESTINATION_ZONE = gettext_noop("Destination zone")
MOVE_TO_ZONE = gettext_noop("Move to zone")

Color = Literal[
    "primary", "secondary", "tertiary", "success", "warning", "danger", "medium"
]
Shape = Literal["square", "round", "rectangle"]
TableStatus = Literal["available", "occupied", "reserved", "blocked"]
SessionStatus = Literal["open", "closed", "transferred", "merged", "parked"]
HoldSource = Literal["manual", "reservation"]
HoldStatus = Literal["held", "consumed", "released", "expired"]
ZoneSort = Literal[
    "sort_order",
    "-sort_order",
    "name",
    "-name",
    "color",
    "-color",
    "table_count",
    "-table_count",
    "available_count",
    "-available_count",
    "is_active",
    "-is_active",
]
TableSort = Literal[
    "number",
    "-number",
    "name",
    "-name",
    "zone_name",
    "-zone_name",
    "capacity",
    "-capacity",
    "status",
    "-status",
]
SessionSort = Literal[
    "opened_at",
    "-opened_at",
    "closed_at",
    "-closed_at",
    "table_number",
    "-table_number",
    "zone_name",
    "-zone_name",
    "guests_count",
    "-guests_count",
    "paid_total",
    "-paid_total",
    "status",
    "-status",
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(100, 1)
Said = _text(100, 1)
Number = _text(20, 1)
Description = _text(500)
Notes = _text(2000)
Guests = Annotated[int, Field(ge=1, le=MAX_GUESTS)]
Seats = Annotated[int, Field(ge=1, le=MAX_CAPACITY)]
Coordinate = Annotated[int, Field(ge=0, le=MAX_PLAN)]
Side = Annotated[int, Field(ge=MIN_BOX, le=MAX_PLAN)]
Minutes = Annotated[int, Field(ge=MIN_MINUTES, le=MAX_MINUTES)]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


def _named(value_id, said, message) -> None:
    if value_id is None and not said:
        raise ValueError(str(message))


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError(str(MOMENT_WITHOUT_ZONE))
    return value


# ── Pages ────────────────────────────────────────────────────────────────────────────────────────


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


# ── References: by id, or as a person says it ────────────────────────────────────────────────────


class ZoneRefIn(In):
    id: UUID | None = Field(None, description="The zone's id.")
    zone: Said | None = Field(
        None, description="The zone's name, when its id is not known (e.g. said aloud)."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.zone, SAY_WHICH_ZONE)
        return self


class TableRefIn(In):
    id: UUID | None = Field(None, description="The table's id.")
    table: Said | None = Field(
        None,
        description="The table's number (or its name), when its id is not known, e.g. «4».",
    )
    zone: Said | None = Field(
        None,
        description="The name of the table's zone, when the same number is in several zones.",
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.table, SAY_WHICH_TABLE)
        return self


class SessionRefIn(In):
    id: UUID | None = Field(None, description="The table check's id.")
    table: Said | None = Field(
        None,
        description="The number of the table the check is open at, when its id is not known.",
    )
    zone: Said | None = Field(
        None, description="The table's zone, when the same number is in several zones."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.table, SAY_WHICH_CHECK)
        return self


class ByIdIn(In):
    id: UUID = Field(description="The id of the record.")


# ── Zones ────────────────────────────────────────────────────────────────────────────────────────


class ZoneListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the zone's name."
    )
    name: str | None = Field(
        None, max_length=100, description="Part of the zone's name (the column filter)."
    )
    color: Color | None = Field(None, description="Only the zones of this colour.")
    is_active: bool | None = Field(
        None, description="Only the active (true) or the inactive (false) zones."
    )
    sort: ZoneSort = Field(
        "sort_order", description="Order; a leading '-' reverses it."
    )


class ZoneIn(In):
    name: Name = Field(description="The zone's name, e.g. Dining room, Terrace, Bar.")
    description: Description = Field(
        "", description="A description of the zone (optional)."
    )
    color: Color = Field(
        "primary", title=ZONE_COLOUR, description="Its colour in the list of zones."
    )
    sort_order: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Its place among the zones; empty = the last one.",
    )


class ZonePatchIn(ZoneRefIn):
    name: Name | None = Field(None, description="The new name.")
    description: Description | None = Field(None, description="The new description.")
    color: Color | None = Field(None, title=ZONE_COLOUR, description="The new colour.")
    sort_order: int | None = Field(
        None, ge=0, le=1_000_000, description="The new place among the zones."
    )
    is_active: bool | None = Field(
        None,
        description="Active (true) or out of service (false): an inactive zone leaves the service view.",
    )


class ZoneOut(Schema):
    id: UUID = Field(description="The zone's id.")
    name: str = Field(description="Name.")
    description: str = Field(description="Description.")
    color: Color = Field(description="Colour.")
    sort_order: int = Field(description="Place among the zones.")
    is_active: bool = Field(description="Whether it is in service.")
    table_count: int = Field(description="Tables in use in the zone.")
    available_count: int = Field(description="Of them, how many are free right now.")


ZonePage = Page[ZoneOut]


# ── Tables ───────────────────────────────────────────────────────────────────────────────────────


class TableListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the table's number or name."
    )
    number: str | None = Field(
        None, max_length=20, description="Part of the table's number."
    )
    name: str | None = Field(
        None, max_length=100, description="Part of the table's name."
    )
    zone_id: UUID | None = Field(None, description="Only the tables of this zone.")
    zone: str | None = Field(
        None, max_length=100, description="Only the tables of the zone with this name."
    )
    status: TableStatus | None = Field(
        None,
        description="Only the tables available, occupied, reserved or blocked right now.",
    )
    shape: Shape | None = Field(None, description="Only the tables of this shape.")
    is_active: bool | None = Field(
        None, description="Only the tables in use (true) or out of use (false)."
    )
    in_service: bool | None = Field(
        None,
        description="Only the tables that serve (active, in an active zone): the service view's.",
    )
    capacity_min: int | None = Field(None, ge=0, description="Fewest seats.")
    capacity_max: int | None = Field(None, ge=0, description="Most seats.")
    sort: TableSort = Field(
        "number",
        description="Order (numbers in natural order); a leading '-' reverses it.",
    )


class TableIn(In):
    zone_id: UUID | None = Field(None, description="The zone it goes in.")
    zone: Said | None = Field(
        None, description="The name of the zone it goes in, when its id is not known."
    )
    number: Number | None = Field(
        None,
        description="Its number or name (S1, Terrace A); empty = the first free number of the zone.",
    )
    name: _text(100) = Field("", description="An optional name.")
    capacity: Seats = Field(4, description="Seats.")
    shape: Shape = Field("square", description="square, round or rectangle.")
    position_x: Coordinate | None = Field(
        None, description="Where on the plan (pixels); empty = the first free spot."
    )
    position_y: Coordinate | None = Field(
        None, description="Where on the plan (pixels); empty = the first free spot."
    )
    width: Side | None = Field(
        None, description=f"Its box on the plan, in pixels ({BOX} by default)."
    )
    height: Side | None = Field(
        None, description=f"Its box on the plan, in pixels ({BOX} by default)."
    )


class TableBulkIn(In):
    zone_id: UUID | None = Field(None, description="The zone they go in.")
    zone: Said | None = Field(
        None, description="The name of the zone they go in, when its id is not known."
    )
    count: int = Field(
        ge=1, le=MAX_BULK, description=f"How many tables (1 to {MAX_BULK})."
    )
    prefix: _text(10) = Field(
        "",
        title=gettext_noop("Number prefix"),
        description="What goes before each number, e.g. T for T1, T2…",
    )
    start_number: int = Field(
        1,
        ge=0,
        le=100_000,
        title=gettext_noop("First number"),
        description="The first number.",
    )
    capacity: Seats = Field(4, description="Seats of each one.")
    shape: Shape = Field("square", description="square, round or rectangle.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.zone_id, self.zone, SAY_WHICH_ZONE)
        return self


class TablePatchIn(TableRefIn):
    number: Number | None = Field(None, description="The new number.")
    name: _text(100) | None = Field(
        None, description="The new name (empty removes it)."
    )
    capacity: Seats | None = Field(None, description="The new seats.")
    shape: Shape | None = Field(None, description="The new shape.")
    move_to_zone_id: UUID | None = Field(
        None, title=MOVE_TO_ZONE, description="The zone it moves to."
    )
    move_to_zone: Said | None = Field(
        None, title=MOVE_TO_ZONE, description="The name of the zone it moves to."
    )
    blocked: bool | None = Field(
        None,
        description="Out of service (true: nobody is seated there) or back in service (false).",
    )
    is_active: bool | None = Field(
        None, description="In use (true) or out of use (false)."
    )


class TableMoveIn(In):
    id: UUID = Field(description="The table's id.")
    position_x: Coordinate = Field(description="Left edge on the plan, in pixels.")
    position_y: Coordinate = Field(description="Top edge on the plan, in pixels.")
    width: Side | None = Field(
        None, description="Its box's width, in pixels; empty keeps it."
    )
    height: Side | None = Field(
        None, description="Its box's height, in pixels; empty keeps it."
    )


class HoldShownOut(Schema):
    label: str = Field(
        description="The name of the reservation ('' once the customer's data was erased)."
    )
    erased: bool = Field(
        description="The customer's personal data was erased: paint «Deleted customer»."
    )
    held_from: dt.datetime = Field(description="When the reservation starts.")
    held_until: dt.datetime = Field(description="When it ends.")
    party_size: int = Field(description="Its guests (0 = not said).")
    reserving: bool = Field(
        description="Whether it already paints the table Reserved (from an hour before)."
    )


class TableCheckOut(Schema):
    id: UUID = Field(description="The table check's id.")
    order_id: UUID | None = Field(description="Its open check of Sales.")
    guests_count: int = Field(description="Guests.")
    opened_at: dt.datetime = Field(description="When they sat down.")
    waiter_name: str = Field(description="Who serves them.")
    customer_id: UUID | None = Field(description="The customer of the check, if any.")
    customer_name: str | None = Field(description="Their name.")
    split_from_id: UUID | None = Field(description="The check it was split from.")


class TableOut(Schema):
    id: UUID = Field(description="The table's id.")
    number: str = Field(description="Number.")
    name: str = Field(description="Name.")
    capacity: int = Field(description="Seats.")
    shape: Shape = Field(description="Shape.")
    status: TableStatus = Field(
        description="available, occupied, reserved or blocked, right now."
    )
    blocked: bool = Field(description="Out of service.")
    is_active: bool = Field(description="In use.")
    zone_id: UUID | None = Field(description="Its zone.")
    zone_name: str | None = Field(description="Its zone's name.")
    in_service: bool = Field(
        description="Active, in an active zone: it shows in the service view."
    )
    position_x: int = Field(description="Left edge on the plan.")
    position_y: int = Field(description="Top edge on the plan.")
    width: int = Field(description="Width of its box.")
    height: int = Field(description="Height of its box.")
    guests: int | None = Field(
        description="Guests seated (all its open checks), when occupied."
    )
    since: dt.datetime | None = Field(description="Since when it is occupied.")
    waiter_name: str = Field(description="Who serves it ('' when free).")
    checks: list[TableCheckOut] = Field(
        description="Its open checks (two after a split), oldest first."
    )
    hold: HoldShownOut | None = Field(
        description="Its earliest reservation of today, if any."
    )


TablePage = Page[TableOut]


class TablesOut(Schema):
    rows: list[TableOut] = Field(description="The tables created.")


# ── Table checks (sessions) ──────────────────────────────────────────────────────────────────────


class SessionListIn(PageIn):
    search: str | None = Field(
        None, max_length=20, description="Part of the table's number."
    )
    table_number: str | None = Field(
        None,
        max_length=20,
        description="Part of the table's number (the column filter).",
    )
    status: SessionStatus | None = Field(
        None,
        description="open, closed, transferred, merged or parked; without it, every check.",
    )
    zone_id: UUID | None = Field(
        None, description="Only the checks of this zone's tables."
    )
    waiter_id: str | None = Field(
        None, max_length=64, description="Only the checks this person opened."
    )
    table_id: UUID | None = Field(None, description="Only the checks of this table.")
    opened_from: dt.date | None = Field(
        None, description="Opened on this business day or later."
    )
    opened_to: dt.date | None = Field(
        None, description="Opened on this business day or earlier."
    )
    sort: SessionSort = Field(
        "-opened_at", description="Order; a leading '-' reverses it."
    )


class SessionOut(Schema):
    id: UUID = Field(description="The table check's id.")
    table_id: UUID | None = Field(description="Its table (none when parked).")
    table_number: str | None = Field(description="Its table's number.")
    zone_id: UUID | None = Field(description="Its table's zone.")
    zone_name: str | None = Field(description="Its zone's name.")
    order_id: UUID | None = Field(description="Its open check of Sales.")
    guests_count: int = Field(description="Guests.")
    status: SessionStatus = Field(
        description="open, closed, transferred, merged or parked."
    )
    waiter_id: str = Field(description="Who opened it (serves it).")
    waiter_name: str = Field(description="Their name.")
    opened_at: dt.datetime = Field(description="When it opened.")
    closed_at: dt.datetime | None = Field(description="When it ended.")
    notes: str = Field(description="Notes.")
    split_from_id: UUID | None = Field(description="The check it was split from.")
    transferred_from_id: UUID | None = Field(
        description="The check it was transferred from."
    )
    merged_into_id: UUID | None = Field(description="The check it was merged into.")
    paid_total: int | None = Field(
        description="What its check of Sales charged, in cents (none yet: null)."
    )
    customer_id: UUID | None = Field(description="The customer of the check, if any.")
    customer_name: str | None = Field(description="Their name.")


SessionPage = Page[SessionOut]


class SessionsOut(Schema):
    rows: list[SessionOut] = Field(description="The table checks.")


class SessionOpenIn(In):
    table_id: UUID | None = Field(None, description="The table to seat.")
    table: Said | None = Field(
        None, description="The number of the table to seat, e.g. «4»."
    )
    zone: Said | None = Field(
        None, description="Its zone, when the same number is in several zones."
    )
    guests_count: Guests | None = Field(
        None,
        description="How many sit; empty = the reservation's guests, else the table's seats.",
    )
    notes: Notes = Field("", description="Notes of the check.")
    order_id: UUID | None = Field(
        None,
        description="An open check of Sales to bring to the table (e.g. a bar check); empty = a new one.",
    )
    customer_id: UUID | None = Field(None, description="The customer of the check.")
    customer: Said | None = Field(
        None,
        title=gettext_noop("Customer"),
        description="The customer's name or phone, when the id is not known.",
    )
    reservation_id: UUID | None = Field(
        None,
        title=gettext_noop("Reservation"),
        description="The reservation whose party sits: only its hold of the table is spent; empty = every hold "
        "already showing the table Reserved.",
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        return self


class SessionCloseIn(SessionRefIn):
    order_id: UUID | None = Field(
        None,
        description="The check of Sales the screen saw on it: a different one now refuses the close.",
    )
    notes: Notes | None = Field(None, description="A note added to the check's notes.")


class SessionTransferIn(SessionRefIn):
    to_table_id: UUID | None = Field(
        None, title=DESTINATION_TABLE, description="The table it goes to."
    )
    to_table: Said | None = Field(
        None, title=DESTINATION_TABLE, description="The number of the table it goes to."
    )
    to_zone: Said | None = Field(
        None,
        title=DESTINATION_ZONE,
        description="That table's zone, when its number repeats.",
    )

    @model_validator(mode="after")
    def _where(self):
        _named(self.to_table_id, self.to_table, SAY_WHERE_TO)
        return self


class SessionMergeIn(SessionRefIn):
    into_session_id: UUID | None = Field(
        None,
        title=gettext_noop("Into check"),
        description="The check that stays (another one of the same table too).",
    )
    into_table_id: UUID | None = Field(
        None, title=DESTINATION_TABLE, description="The table whose check stays."
    )
    into_table: Said | None = Field(
        None,
        title=DESTINATION_TABLE,
        description="The number of the table whose check stays.",
    )
    into_zone: Said | None = Field(
        None,
        title=DESTINATION_ZONE,
        description="That table's zone, when its number repeats.",
    )

    @model_validator(mode="after")
    def _where(self):
        if self.into_session_id is None:
            _named(self.into_table_id, self.into_table, SAY_WHICH_TARGET)
        return self


class SessionSplitIn(SessionRefIn):
    line_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        title=gettext_noop("Lines to move"),
        description="The lines of its check of Sales that move to the new check; none = a blank one.",
    )
    guests_count: Guests = Field(1, description="Guests of the new check.")
    notes: Notes = Field("", description="Notes of the new check.")


class SessionGuestsIn(SessionRefIn):
    guests_count: Guests = Field(description="How many sit now.")


class SessionRestoreIn(In):
    id: UUID = Field(description="The parked check.")
    table_id: UUID | None = Field(None, description="The table it sits at.")
    table: Said | None = Field(None, description="The number of the table it sits at.")
    zone: Said | None = Field(
        None, description="That table's zone, when its number repeats."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        return self


class SessionLinkOrderIn(SessionRefIn):
    order_id: UUID = Field(
        description="The open check of Sales that becomes the table's."
    )


class ByOrderIn(In):
    order_id: UUID = Field(description="The check of Sales.")


class SplitOut(Schema):
    session: SessionOut = Field(description="The check that was split.")
    new_session: SessionOut = Field(description="The new check, at the same table.")


class ClosedOut(Schema):
    closed: int = Field(description="How many table checks were closed.")


# ── Waiters, floor and settings ──────────────────────────────────────────────────────────────────


class WaiterListIn(PageIn):
    search: str | None = Field(
        None, max_length=128, description="Part of the person's name."
    )


class WaiterOut(Schema):
    id: str = Field(description="The person's id.")
    name: str = Field(description="Their name.")


WaiterPage = Page[WaiterOut]


class FloorStatusOut(Schema):
    usable_tables: int = Field(
        description="Tables in use (not deleted, active): the plan is set up with one."
    )
    zones: int = Field(description="Zones of the room.")


class SettingsOut(Schema):
    prompt_guests_on_seat: bool = Field(
        description="Ask the guests when seating a table."
    )
    timer_warning_minutes: int = Field(
        description="An open check turns amber after these minutes."
    )
    timer_critical_minutes: int = Field(description="And red after these.")
    reserved_lead_minutes: int = Field(
        description="A reservation paints its table Reserved this long before."
    )
    timezone: str = Field(description="The business's time zone (IANA).")


class SettingsIn(In):
    prompt_guests_on_seat: bool | None = Field(
        None, description="Ask the guests when seating a table."
    )
    timer_warning_minutes: Minutes | None = Field(
        None, description="Amber after these minutes (1 to 600)."
    )
    timer_critical_minutes: Minutes | None = Field(
        None, description="Red after these minutes (1 to 600)."
    )


# ── Holds ────────────────────────────────────────────────────────────────────────────────────────


class HoldPlaceIn(In):
    table_id: UUID | None = Field(None, description="The table to hold.")
    table: Said | None = Field(None, description="The number of the table to hold.")
    zone: Said | None = Field(
        None, description="Its zone, when the same number is in several zones."
    )
    source_ref: _text(100, 1) = Field(
        description="A reference of this hold: asking again with it changes the same hold."
    )
    held_from: dt.datetime = Field(description="When it starts, with its time zone.")
    held_until: dt.datetime = Field(description="When it ends, with its time zone.")
    party_size: int = Field(
        0, ge=0, le=MAX_GUESTS, description="Guests expected (0 = not said)."
    )
    label: _text(200) = Field(
        "", description="The name painted on the table, e.g. Pedro."
    )

    @field_validator("held_from", "held_until")
    @classmethod
    def _zoned(cls, value):
        return _aware(value)

    @model_validator(mode="after")
    def _window(self):
        _named(self.table_id, self.table, SAY_WHICH_TABLE)
        if self.held_until <= self.held_from:
            raise ValueError(str(HOLD_ENDS_BEFORE))
        return self


class HoldReleaseIn(In):
    source: HoldSource = Field(
        "manual", description="Who held it: manual (by hand) or reservation."
    )
    source_ref: _text(100, 1) = Field(description="The hold's reference.")


class HoldOut(Schema):
    id: UUID = Field(description="The hold's id.")
    table_id: UUID = Field(description="The table held.")
    source: HoldSource = Field(description="manual or reservation.")
    source_ref: str = Field(description="Its reference.")
    held_from: dt.datetime = Field(description="When it starts.")
    held_until: dt.datetime = Field(description="When it ends.")
    party_size: int = Field(description="Guests expected.")
    label: str = Field(description="The name painted.")
    status: HoldStatus = Field(description="held, consumed, released or expired.")


class ExpiredOut(Schema):
    expired: int = Field(description="How many holds expired.")


class HoldsChangedOut(Schema):
    changed: int = Field(description="How many holds changed.")


class ReservationStatusIn(Reaction):
    """``reservation.reservation.status_changed``: the reservation with its table and its window."""

    id: str = Field(description="The reservation's id.")
    status: str = Field(
        description="Its new status: confirmed, seated, completed, cancelled, no_show…"
    )
    table_id: UUID | None = Field(None, description="Its table, if it has one.")
    date: dt.date | None = Field(None, description="Its day (the business's).")
    time: dt.time | None = Field(
        None, description="Its time (the business's wall clock)."
    )
    duration_minutes: int | None = Field(
        None, ge=1, le=24 * 60, description="How long it lasts (120 if not said)."
    )
    party_size: int | None = Field(None, ge=0, le=MAX_GUESTS, description="Its guests.")
    guest_name: str = Field(
        "",
        max_length=200,
        title=gettext_noop("Guest's name"),
        description="The name on the reservation.",
    )
    customer_id: UUID | None = Field(None, description="Its customer's card, if any.")


class ReservationUpdatedIn(ReservationStatusIn):
    """``reservation.reservation.updated``: the fields that changed. ``table_id`` sent empty = the
    reservation lost its table; not sent = unchanged."""

    status: str = Field("", description="Its status, if it changed.")


class CustomerErasedIn(Reaction):
    """``customer.customer.erased``: the card whose personal data was erased."""

    id: UUID | None = Field(None, description="The erased customer's card.")
