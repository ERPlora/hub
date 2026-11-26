"""What the live floor paints of each table (``table.table.list``, ``table.table.get``): its status right now, its
open checks and its next reservation of today."""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema

from apps.table.schemas.fields import Page, Shape, TableStatus


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
    label: str = Field(
        description="The table as the room's screens name it, in the reader's language: its number with its zone "
        "(«5 (Terrace)»), since the number repeats across zones."
    )
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
    amount: int | None = Field(
        description="What is left to charge on all its open checks of Sales, in cents of the business's currency, "
        "when occupied (0 while nothing is ordered); null otherwise.",
        json_schema_extra={"money": True},
    )
    bill_requested: bool = Field(
        description="Whether it has asked for the bill: the bill of one of its open checks was printed for the table in "
        "Sales. It stays until that check is charged in full or deleted; false when nobody sits at it."
    )


TablePage = Page[TableOut]


class TablesOut(Schema):
    rows: list[TableOut] = Field(description="The tables created.")
