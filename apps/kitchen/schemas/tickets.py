"""A ticket and its dishes as every read and write returns them; the list of tickets, the tickets of a check
and the device notices; a ticket made by hand, and what a person does with one: cancel it, rush it, mark its
dishes ready or recall them."""

import datetime as dt
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from ninja import Field, Schema
from pydantic import field_validator, model_validator

from apps.kitchen.schemas.fields import (
    A_DISH,
    A_PRODUCT,
    ADD_A_DISH,
    DISHES,
    MAX_ITEMS,
    SAY_WHAT_DISH,
    Destination,
    In,
    ItemStatus,
    Label,
    Note,
    Notes,
    OrderType,
    Page,
    PageIn,
    PrinterUsage,
    Priority,
    Quantity,
    Reason,
    Said,
    StationScope,
    TicketRefIn,
    TicketSort,
    TicketStatus,
    _text,
)
from base.allergens import Allergy, AllergyInDish
from base.schemas.assistant import IN_OWN_WORDS


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
    allergy: Allergy
    allergy_in_dish: AllergyInDish


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
        description="Informative total in cents (the kitchen never charges).", json_schema_extra={"money": True}
    )
    saved: bool = Field(
        description="False for a round of Sales the kitchen shows but has not saved yet."
    )
    items: list[ItemOut] = Field(description="Its dishes, in order.")
    print_error: str | None = Field(
        None,
        description="After an action that asked for paper: why Printing refused it; none when it did not.",
    )


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
    total: int = Field(description="Informative total in cents.", json_schema_extra={"money": True})
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


class NoticesIn(In):
    since: dt.datetime | None = Field(
        None, description="Only tickets received from this instant on; empty = the last 24 hours."
    )
    limit: int = Field(20, ge=1, le=50, description="How many notices, the newest first (1 to 50).")


class NoticeOut(Schema):
    id: UUID = Field(description="The ticket's id, the same before and after the relay saves it.")
    at: dt.datetime = Field(description="When the ticket was received.")
    number: str = Field(description="The ticket's number, YYYYMMDD-NNNN.")
    label: str = Field(description="Where the ticket goes; empty when it has no label.")
    dish_names: str = Field(description="The dishes, separated by commas.")
    waiter: str = Field(description="Who attends the check; empty when nobody is named.")


class NoticesOut(Schema):
    rows: list[NoticeOut] = Field(description="The new tickets, the newest first.")


class ManualItemIn(In):
    product_id: UUID | None = Field(None, description="A product of the catalogue.", json_schema_extra=A_PRODUCT)
    product: Said | None = Field(
        None, description="A product of the catalogue by its name.", json_schema_extra={"name_of": "product_id"}
    )
    name: _text(200) = Field(
        "", description="What to cook, when it is not a product of the catalogue.", json_schema_extra=IN_OWN_WORDS
    )
    quantity: Quantity = Field(Decimal("1"), description="How many.")
    notes: Note = Field("", description="A note for the cook.", json_schema_extra=IN_OWN_WORDS)

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
        title=DISHES, description="Its dishes (at least one).", max_length=MAX_ITEMS
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
    item_ids: list[Annotated[UUID, Field(json_schema_extra=A_DISH)]] = Field(
        default_factory=list,
        title=DISHES,
        description="The dishes; empty: every dish of the ticket in the station's scope.",
    )
    station: StationScope


class ItemRecallIn(ItemBumpIn):
    pass
