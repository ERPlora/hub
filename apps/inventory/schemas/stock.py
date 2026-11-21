"""Schemas of the stock: receptions, counts, write-offs, the products low on stock and the summary."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.inventory.schemas.fields import (
    MAX_BATCH,
    Cents,
    Page,
    PageIn,
    ProductSearch,
    Quantity,
    UnitCode,
    _ProductLineRef,
    _text,
)

LowStockSort = Literal[
    "name",
    "-name",
    "sku",
    "-sku",
    "stock",
    "-stock",
    "low_stock_threshold",
    "-low_stock_threshold",
]

Reason = _text(500, 3)


class LowStockListIn(PageIn):
    search: ProductSearch = None
    sku: str | None = Field(None, max_length=64, description="This exact SKU.")
    stock_min: Quantity | None = Field(None, description="Lowest stock.")
    stock_max: Quantity | None = Field(None, description="Highest stock.")
    sort: LowStockSort = Field(
        "stock",
        description="Order (the one with less first by default); a leading '-' reverses it.",
    )


class SummaryIn(Schema):
    pass


class ReceiveLineIn(_ProductLineRef):
    qty: Quantity = Field(gt=0, description="Quantity received, in the product's unit.")
    unit_cost: Cents | None = Field(
        None, description="Cost per unit in cents; null keeps the cost the product had."
    )


class ReceiveIn(Schema):
    items: list[ReceiveLineIn] = Field(
        min_length=1, max_length=MAX_BATCH, title=gettext_noop("Products"), description="The products received."
    )
    reference: _text(200) = Field("", description="The delivery note's number.")


class CountIn(_ProductLineRef):
    stock: Quantity = Field(
        ge=0, title=gettext_noop("Counted stock"), description="What there really is: the total counted, not the difference."
    )
    reason: Reason = Field(description="Why (3 to 500 characters).")


class WriteOffIn(_ProductLineRef):
    qty: Quantity = Field(
        gt=0, description="Quantity written off, in the product's unit."
    )
    reason: Reason = Field(
        description="Why: waste, breakage, own consumption… (3 to 500 characters)."
    )


class LowStockOut(Schema):
    id: UUID = Field(description="The product's id.")
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU.")
    stock: Decimal = Field(description="Current stock.")
    low_stock_threshold: Decimal = Field(description="Its threshold.")
    unit: UnitCode = Field(description="Unit of measure.")
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: UnitCode = Field(description="Unit the price refers to.")


LowStockPage = Page[LowStockOut]


class SummaryOut(Schema):
    products_tracked: int = Field(description="Active articles with stock control.")
    products_in_stock: int = Field(description="Of them, with stock above zero.")
    products_out_of_stock: int = Field(description="Of them, at zero or below.")
    products_low_stock: int = Field(description="Of them, at or under their threshold.")
    products_without_cost: int = Field(
        description="Of them, without a cost: the value is partial."
    )
    stock_value: int = Field(
        description="Σ cost × stock of the ones in stock, in cents.", json_schema_extra={"money": True}
    )
    active_products: int = Field(description="Every active product, services included.")
