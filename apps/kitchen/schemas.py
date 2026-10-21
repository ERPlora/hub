"""Input and output schemas of the kitchen app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. A record is named
by its id or, as a person says it (assistant, voice), by its number or its name: a ticket by its number
(«12», «#0012», «20261014-0012») or its label («Table 4»); a station by its name («grill») or «none» for
the dishes with no station; a product or a category of Inventory by its name. Every input refuses a field
it does not declare; an edit changes only the fields it sends. Moments travel ISO 8601 with their zone;
money in cents.

The inputs of the reactions to Sales' events read only what they need from the emitter's payload and
ignore the rest, never refuse it.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

T = TypeVar("T")

#: The most dishes a ticket made by hand takes.
MAX_ITEMS = 100

SAY_WHICH_TICKET = _("Say which ticket: its id, its number or its label.")
SAY_WHICH_STATION = _("Say which station: its id or its name.")
SAY_PRODUCT_OR_CATEGORY = _("Say one product or one category, not both.")
SAY_WHAT_DISH = _("Say which dish: a product of the catalogue or its name.")
ADD_A_DISH = _("Add at least one dish.")

TicketStatus = Literal["pending", "preparing", "ready", "served", "cancelled"]
ItemStatus = Literal["pending", "preparing", "ready", "served", "cancelled", "voided"]
OrderType = Literal["dine_in", "takeaway", "delivery"]
Priority = Literal["normal", "rush", "vip"]
Destination = Literal["both", "display", "printer"]
PrinterUsage = Literal["kitchen", "bar"]
SoundTone = Literal["chime", "bell", "buzzer"]
LogAction = Literal[
    "received",
    "created",
    "started",
    "ready",
    "item_ready",
    "item_recalled",
    "item_voided",
    "served",
    "recalled",
    "cancelled",
    "rushed",
    "unrushed",
    "reprinted",
    "deleted",
]
TicketSort = Literal[
    "received_at",
    "-received_at",
    "number",
    "-number",
    "status",
    "-status",
    "total",
    "-total",
]
StationSort = Literal[
    "sort_order", "-sort_order", "name", "-name", "in_progress", "-in_progress"
]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Said = _text(120, 1)
Label = _text(120)
Notes = _text(2000)
Note = _text(255)
Reason = _text(255)
Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Minutes = Annotated[int, Field(ge=1, le=120)]
Volume = Annotated[int, Field(ge=0, le=100)]
Quantity = Annotated[
    Decimal, Field(gt=0, le=Decimal("9999"), max_digits=12, decimal_places=3)
]


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class Reaction(Schema):
    """The input of a reaction to another app's event: what it needs, the rest of the payload ignored."""

    model_config = ConfigDict(extra="ignore")


def _named(value_id, said, message) -> None:
    if value_id is None and not said:
        raise ValueError(str(message))


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


# ── References ───────────────────────────────────────────────────────────────────────────────────


class TicketRefIn(In):
    ticket_id: UUID | None = Field(None, description="The ticket's id.")
    ticket: Said | None = Field(
        None,
        description="The ticket as a person says it: its number («12», «#0012», «20261014-0012») or its label "
        "(«Table 4»), when its id is not known.",
    )

    @model_validator(mode="after")
    def _ticket_named(self):
        _named(self.ticket_id, self.ticket, SAY_WHICH_TICKET)
        return self


class StationRefIn(In):
    station_id: UUID | None = Field(None, description="The station's id.")
    station: Said | None = Field(
        None, description="The station's name («grill»), when its id is not known."
    )

    @model_validator(mode="after")
    def _station_named(self):
        _named(self.station_id, self.station, SAY_WHICH_STATION)
        return self


StationScope = Annotated[
    str | None,
    Field(
        None,
        max_length=120,
        description="Only one station: its id or its name («grill»), or «none» for the dishes with no "
        "station. Without it, every station (the pass).",
    ),
]


# ── The board ────────────────────────────────────────────────────────────────────────────────────


class BoardIn(In):
    station: StationScope


class ItemOut(Schema):
    id: UUID = Field(
        description="The dish's id (for a round of a check, the id of its line of Sales; for a dish of a menu, "
        "one derived from it)."
    )
    position: int = Field(description="Its place in the ticket.")
    product_id: UUID | None = Field(description="Inventory's product, if it is one.")
    name: str = Field(description="What to cook.")
    quantity: Decimal = Field(description="How many.")
    unit: str = Field(description="Unit of the quantity.")
    notes: str = Field(description="The waiter's note.")
    modifiers: list[str] = Field(
        description="The options chosen in the till, by the names the cook reads, in the order chosen."
    )
    menu_name: str = Field(
        description="The header of the menu it is a dish of (its kitchen name, else its name); empty if none."
    )
    menu_line_id: UUID | None = Field(
        description="The menu's line of the check: the dishes of one menu share it; none out of a menu."
    )
    station_id: UUID | None = Field(
        description="The station it went to; none = «No station»."
    )
    station_name: str = Field(
        description="The station's name (the live one; the frozen one if it is gone)."
    )
    station_color: str = Field(
        description="The station's colour (#RRGGBB); empty with no station."
    )
    destination: Destination = Field(
        description="both, display (screen only) or printer (paper only)."
    )
    printer_usage: PrinterUsage = Field(
        description="The printer function it prints on: kitchen or bar."
    )
    status: ItemStatus = Field(
        description="pending, preparing, ready, served, cancelled or voided."
    )
    void_reason: str = Field(description="Why the till voided it.")
    ready_at: dt.datetime | None = Field(description="When it was marked ready.")


class TicketOut(Schema):
    id: UUID = Field(description="The ticket's id.")
    number: str = Field(description="Its number, YYYYMMDD-NNNN (the business day).")
    short_number: str = Field(
        description="The last four digits, as the card shows them (#0012)."
    )
    label: str = Field(description="Where it goes (Table 4); empty: its type says it.")
    order_type: OrderType = Field(description="dine_in, takeaway or delivery.")
    priority: Priority = Field(description="normal, rush or vip.")
    status: TicketStatus = Field(
        description="pending, preparing, ready, served or cancelled."
    )
    round_no: int = Field(description="The round of its check (1 the first).")
    waiter: str = Field(description="Who sent it.")
    notes: str = Field(description="Notes of the whole ticket.")
    order_id: UUID | None = Field(
        description="The check of Sales it came from; none for one made by hand."
    )
    received_at: dt.datetime = Field(
        description="When it was sent (the card's clock counts from here)."
    )
    started_at: dt.datetime | None = Field(description="When the kitchen started it.")
    ready_at: dt.datetime | None = Field(description="When it was ready.")
    served_at: dt.datetime | None = Field(description="When it was served.")
    cancelled_at: dt.datetime | None = Field(description="When it was cancelled.")
    rush_count: int = Field(description="How many times it was rushed.")
    total: int = Field(
        description="Informative total in cents (the kitchen never charges)."
    )
    saved: bool = Field(
        description="False for a round of Sales the kitchen shows but has not saved yet."
    )
    items: list[ItemOut] = Field(description="Its dishes, in order.")
    print_error: str | None = Field(
        None,
        description="After an action that asked for paper: why Printing refused it; none when it did not.",
    )


class StationChipOut(Schema):
    id: UUID | None = Field(description="The station; none = «No station».")
    name: str = Field(description="Its name.")
    color: str = Field(description="Its colour (#RRGGBB); empty with no station.")


class BoardOut(Schema):
    cooking: list[TicketOut] = Field(
        description="The tickets being cooked: rush, then VIP, then the rest, oldest first."
    )
    ready: list[TicketOut] = Field(
        description="The tickets waiting at the pass, oldest first."
    )
    cooking_count: int = Field(description="How many tickets are being cooked.")
    ready_count: int = Field(description="How many tickets wait at the pass.")
    stations: list[StationChipOut] = Field(
        description="The stations the dishes on the board go to."
    )
    truncated: bool = Field(
        description="More tickets are on the line than the board shows (200)."
    )


class AllDayIn(In):
    station: StationScope


class AllDayRowOut(Schema):
    product_id: UUID | None = Field(description="Inventory's product, if it is one.")
    name: str = Field(description="The dish.")
    unit: str = Field(description="Its unit.")
    station_id: UUID | None = Field(description="Its station; none = «No station».")
    station_name: str = Field(description="The station's name.")
    quantity: Decimal = Field(description="How many are left to cook.")


class AllDayOut(Schema):
    rows: list[AllDayRowOut] = Field(description="What is left to cook, most first.")


# ── Tickets ──────────────────────────────────────────────────────────────────────────────────────


class TicketListIn(PageIn):
    search: str | None = Field(
        None, max_length=120, description="Part of the number or of the label."
    )
    status: TicketStatus | None = Field(
        None, description="Only tickets of this status."
    )
    order_type: OrderType | None = Field(None, description="Only tickets of this type.")
    priority: Priority | None = Field(
        None, description="Only tickets of this priority."
    )
    sort: TicketSort = Field(
        "-received_at", description="Order: a field, «-» first for descending."
    )


class TicketRowOut(Schema):
    id: UUID = Field(description="The ticket's id.")
    number: str = Field(description="Its number, YYYYMMDD-NNNN.")
    short_number: str = Field(description="Its last four digits.")
    label: str = Field(description="Where it goes.")
    order_type: OrderType = Field(description="dine_in, takeaway or delivery.")
    priority: Priority = Field(description="normal, rush or vip.")
    status: TicketStatus = Field(
        description="pending, preparing, ready, served or cancelled."
    )
    round_no: int = Field(description="The round of its check.")
    items_count: int = Field(
        description="How many dishes still count (not voided nor cancelled)."
    )
    total: int = Field(description="Informative total in cents.")
    received_at: dt.datetime = Field(description="When it was sent.")
    order_id: UUID | None = Field(description="The check of Sales it came from.")
    saved: bool = Field(description="False for a round the kitchen has not saved yet.")


TicketPage = Page[TicketRowOut]


class ByOrderIn(In):
    order_id: UUID = Field(description="The check of Sales.")


class TicketsOut(Schema):
    tickets: list[TicketOut] = Field(
        description="The tickets of the check, the newest round first."
    )


class TicketSendIn(In):
    order_id: UUID = Field(
        description="The open check whose pending lines go to the kitchen."
    )
    label: Label = Field(
        "",
        description="What the kitchen reads as the check's name (Table 4); empty: the check's title.",
    )
    channel: OrderType = Field("dine_in", description="dine_in, takeaway or delivery.")
    priority: Literal["normal", "rush"] = Field(
        "normal", description="rush sends it urgent."
    )


_PRIORITIES = {"urgent": "rush", "rush": "rush", "vip": "vip"}
_CHANNELS = {"dine_in", "takeaway", "delivery"}


class ReceivedItemIn(Reaction):
    order_item_id: UUID = Field(description="The line of Sales sent.")


class TicketReceiveIn(Reaction):
    """``sale.order.fired`` as Sales sends it (its WORKBOOK «Lo que avisa»)."""

    order_id: UUID = Field(description="The check the round was fired from.")
    round_no: int = Field(ge=1, description="The round fired.")
    label: str = Field("", description="What the kitchen reads as the check's name.")
    channel: str = Field(
        "dine_in",
        description="dine_in, takeaway or delivery; anything else is dine_in.",
    )
    priority: str = Field(
        "", description="urgent or rush (rush), vip; anything else is normal."
    )
    waiter: str = Field("", description="Who sent it.")
    items: list[ReceivedItemIn] = Field(
        default_factory=list, description="The lines sent."
    )

    @field_validator("label", "waiter", mode="before")
    @classmethod
    def _short(cls, value):
        return (value or "")[:120] if isinstance(value, str) else ""

    @field_validator("channel", mode="before")
    @classmethod
    def _channel(cls, value):
        return value if value in _CHANNELS else "dine_in"

    @field_validator("priority", mode="before")
    @classmethod
    def _priority(cls, value):
        return _PRIORITIES.get(str(value or "").strip().lower(), "normal")


class ReceivedOut(Schema):
    ticket: TicketOut | None = Field(
        description="The ticket of the round; none when it had nothing to cook."
    )


class TicketSyncIn(Reaction):
    """A check Sales charged, voided or whose line it voided (``order_id``), or merged (``to_order_id``)."""

    order_id: UUID | None = Field(None, description="The check Sales changed.")
    from_order_id: UUID | None = Field(
        None, description="The check absorbed by a merge."
    )
    to_order_id: UUID | None = Field(
        None, description="The check that stays after a merge."
    )


class SyncOut(Schema):
    received: int = Field(description="Rounds the kitchen saved.")
    changed: int = Field(description="Tickets whose state changed with what Sales did.")


class ManualItemIn(In):
    product_id: UUID | None = Field(None, description="A product of the catalogue.")
    product: Said | None = Field(
        None, description="A product of the catalogue by its name."
    )
    name: _text(200) = Field(
        "", description="What to cook, when it is not a product of the catalogue."
    )
    quantity: Quantity = Field(Decimal("1"), description="How many.")
    notes: Note = Field("", description="A note for the cook.")

    @model_validator(mode="after")
    def _dish_named(self):
        if self.product_id is None and not self.product and not self.name:
            raise ValueError(str(SAY_WHAT_DISH))
        return self


class TicketCreateIn(In):
    order_type: OrderType | None = Field(
        None, description="dine_in, takeaway or delivery; none: the settings' default."
    )
    label: Label = Field("", description="Where it goes (Staff, Table 4).")
    notes: Notes = Field("", description="Notes for the whole ticket.")
    items: list[ManualItemIn] = Field(
        description="Its dishes (at least one).", max_length=MAX_ITEMS
    )

    @field_validator("items")
    @classmethod
    def _some(cls, value):
        if not value:
            raise ValueError(str(ADD_A_DISH))
        return value


class TicketCancelIn(TicketRefIn):
    reason: Reason = Field(
        "", description="Why it is cancelled (it shows in the History)."
    )


class TicketRushIn(TicketRefIn):
    rush: bool = Field(True, description="True rushes it; false takes the rush away.")


class ItemBumpIn(TicketRefIn):
    item_ids: list[UUID] = Field(
        default_factory=list,
        description="The dishes; empty: every dish of the ticket in the station's scope.",
    )
    station: StationScope


class ItemRecallIn(ItemBumpIn):
    pass


# ── Stations and routing ─────────────────────────────────────────────────────────────────────────


class StationListIn(PageIn):
    search: str | None = Field(None, max_length=120, description="Part of the name.")
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) stations."
    )
    sort: StationSort = Field(
        "sort_order", description="Order: a field, «-» first for descending."
    )


class StationOut(Schema):
    id: UUID = Field(description="The station's id.")
    name: str = Field(description="Its name.")
    color: str = Field(description="Its colour, #RRGGBB.")
    destination: Destination = Field(
        description="both, display (screen only) or printer (paper only)."
    )
    printer_usage: PrinterUsage = Field(
        description="kitchen or bar: the printer function."
    )
    printer_name: str = Field(
        description="A given printer by its name; empty: the function's."
    )
    sort_order: int = Field(description="Its place.")
    is_active: bool = Field(description="Whether new dishes go to it.")
    in_progress: int = Field(description="Its dishes still to cook.")
    routes: int = Field(description="How many products and categories go to it.")


StationPage = Page[StationOut]


class StationIn(In):
    name: _text(80, 1) = Field(description="Its name (Grill).")
    color: Hex = Field("#F97316", description="Its colour, #RRGGBB.")
    destination: Destination = Field(
        "both", description="both (screen and paper), display or printer."
    )
    printer_usage: PrinterUsage = Field(
        "kitchen", description="The printer function: kitchen or bar."
    )
    printer_name: _text(100) = Field(
        "",
        description="A given printer of Printing by its name; empty: the function's.",
    )
    sort_order: int = Field(0, ge=0, le=10_000, description="Its place in the lists.")
    is_active: bool = Field(True, description="Whether new dishes go to it.")


class StationPatchIn(StationRefIn):
    name: _text(80, 1) | None = Field(None, description="Its new name.")
    color: Hex | None = Field(None, description="Its colour, #RRGGBB.")
    destination: Destination | None = Field(
        None, description="both, display or printer."
    )
    printer_usage: PrinterUsage | None = Field(None, description="kitchen or bar.")
    printer_name: _text(100) | None = Field(
        None, description="A given printer by its name; empty: the function's."
    )
    sort_order: int | None = Field(None, ge=0, le=10_000, description="Its place.")
    is_active: bool | None = Field(None, description="Whether new dishes go to it.")


class RoutingListIn(PageIn):
    station: StationScope
    search: str | None = Field(
        None,
        max_length=120,
        description="Part of the product's or the category's name.",
    )


class RouteOut(Schema):
    kind: Literal["product", "category"] = Field(description="A product or a category.")
    target_id: UUID = Field(description="The product's or the category's id.")
    target_name: str = Field(description="Its name.")
    station_id: UUID = Field(description="The station it goes to.")
    station_name: str = Field(description="The station's name.")


RoutingPage = Page[RouteOut]


class _Target(In):
    product_id: UUID | None = Field(None, description="A product of Inventory.")
    product: Said | None = Field(
        None, description="A product of Inventory by its name."
    )
    category_id: UUID | None = Field(None, description="A category of Inventory.")
    category: Said | None = Field(
        None, description="A category of Inventory by its name."
    )

    @model_validator(mode="after")
    def _one_target(self):
        product = self.product_id is not None or bool(self.product)
        category = self.category_id is not None or bool(self.category)
        if product == category:
            raise ValueError(str(SAY_PRODUCT_OR_CATEGORY))
        return self


class RoutingSetIn(_Target):
    station_id: UUID | None = Field(None, description="The station it goes to.")
    station: Said | None = Field(None, description="The station by its name.")

    @model_validator(mode="after")
    def _station_named(self):
        _named(self.station_id, self.station, SAY_WHICH_STATION)
        return self


class RoutingClearIn(_Target):
    pass


# ── Settings and history ─────────────────────────────────────────────────────────────────────────


class SettingsOut(Schema):
    show_timer: bool = Field(description="The card shows its clock.")
    warning_minutes: int = Field(
        description="The card turns amber after these minutes."
    )
    critical_minutes: int = Field(description="The card turns red after these minutes.")
    color_coding: bool = Field(
        description="The card's border follows the clock (green, amber, red)."
    )
    sound_enabled: bool = Field(
        description="The display rings when a ticket arrives or is rushed."
    )
    sound_volume: int = Field(description="Volume, 0 to 100.")
    sound_tone: SoundTone = Field(description="chime, bell or buzzer.")
    print_pass: bool = Field(description="Prints the pass when a ticket is ready.")
    works_from_screen: bool = Field(
        description="False: the kitchen cooks from paper and charging serves the rounds."
    )
    default_order_type: OrderType = Field(
        description="The type a ticket made by hand starts with."
    )
    timezone: str = Field(
        description="The business's time zone (dates of the History, the ticket's day)."
    )


class SettingsPatchIn(In):
    show_timer: bool | None = Field(None, description="The card shows its clock.")
    warning_minutes: Minutes | None = Field(
        None, description="Amber after these minutes (1 to 120)."
    )
    critical_minutes: Minutes | None = Field(
        None, description="Red after these minutes (1 to 120), after the amber."
    )
    color_coding: bool | None = Field(
        None, description="The card's border follows the clock."
    )
    sound_enabled: bool | None = Field(
        None, description="Ring when a ticket arrives or is rushed."
    )
    sound_volume: Volume | None = Field(None, description="Volume, 0 to 100.")
    sound_tone: SoundTone | None = Field(None, description="chime, bell or buzzer.")
    print_pass: bool | None = Field(
        None, description="Print the pass when a ticket is ready."
    )
    works_from_screen: bool | None = Field(
        None, description="False if nobody marks anything on the screen."
    )
    default_order_type: OrderType | None = Field(
        None, description="The type a ticket made by hand starts with."
    )


class LogListIn(PageIn):
    search: str | None = Field(
        None, max_length=120, description="Part of the ticket's number or of the notes."
    )
    action: LogAction | None = Field(None, description="Only this action.")
    ticket_id: UUID | None = Field(None, description="Only the history of this ticket.")
    date_from: dt.date | None = Field(
        None, description="From this day (the business's), included."
    )
    date_to: dt.date | None = Field(
        None, description="Up to this day (the business's), included."
    )


class LogOut(Schema):
    id: UUID = Field(description="The entry's id.")
    action: LogAction = Field(description="What happened.")
    ticket_id: UUID = Field(description="The ticket.")
    ticket_number: str = Field(description="The ticket's number.")
    item_name: str = Field(description="The dish, for an action on one dish.")
    station_name: str = Field(description="The station of that dish.")
    actor: str = Field(description="Who did it (empty: the system).")
    notes: str = Field(description="Its notes (a reason).")
    created_at: dt.datetime = Field(description="When.")


LogPage = Page[LogOut]
