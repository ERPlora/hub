"""Schemas of the stock ledger: its list and how a movement reads."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.inventory.schemas.fields import Page, PageIn
from base.sensitive import COSTS

MovementType = Literal["initial", "reception", "sale", "void", "count", "write_off", "refund"]
MovementSort = Literal[
    "created_at",
    "-created_at",
    "movement_type",
    "-movement_type",
    "qty",
    "-qty",
    "stock_after",
    "-stock_after",
]


class MovementListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the product's name or SKU, or of the reference.",
    )
    movement_type: MovementType | None = Field(
        None, description="initial, reception, sale, void, count, write_off or refund."
    )
    reference: str | None = Field(
        None,
        max_length=200,
        description="Part of the reference (the sale or the delivery note).",
    )
    product_id: UUID | None = Field(
        None, description="Only the movements of this product."
    )
    created_from: datetime | None = Field(
        None, description="Only movements made at or after this moment."
    )
    created_to: datetime | None = Field(
        None, description="Only movements made at or before this moment."
    )
    sort: MovementSort = Field(
        "-created_at",
        description="Order (most recent first by default); a leading '-' reverses it.",
    )


class MovementOut(Schema):
    id: UUID = Field(description="The movement's id.")
    product_id: UUID = Field(description="The product it moved.")
    product_name: str = Field(description="The product's name.")
    sku: str = Field(description="The product's SKU.")
    movement_type: MovementType = Field(
        description="initial, reception, sale, void, count, write_off or refund."
    )
    qty: Decimal = Field(description="What the balance changed by (with its sign).")
    stock_after: Decimal = Field(description="The balance it left.")
    reason: str = Field(description="Why (counts and write-offs).")
    reference: str = Field(
        description="The sale (sales and voids) or the delivery note (receptions)."
    )
    reference_label: str = Field(
        description="The reference as a person reads it: for a sale, void or refund, the number of its ticket or "
        "invoice (or the sale's own number), empty when Inventory never learnt it; else the reference itself."
    )
    unit_cost: int | None = Field(
        description="Cost per unit in cents (receptions); null for whoever does not see the costs.",
        json_schema_extra={"money": True, **COSTS},
    )
    actor: str = Field(description="Who made it.")
    created_at: datetime = Field(description="When.")


MovementPage = Page[MovementOut]
