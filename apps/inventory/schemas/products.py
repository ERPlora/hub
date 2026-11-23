"""Schemas of the products: their lists and filters, create, edit, sold out and restore, and how a product reads."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict

from apps.inventory.schemas.fields import (
    A_CATEGORY,
    CATEGORIES,
    MAX_BATCH,
    TAX_CATEGORY,
    T_PRODUCT,
    Cents,
    Description,
    Page,
    PageIn,
    ProductRefIn,
    ProductSearch,
    Quantity,
    TaxKey,
    UnitCode,
    _text,
)
from apps.tax.schemas import A_TAX_CATEGORY
from base.allergens import AllergensIn, AllergensOut, AllergensPatchIn
from base.recovery import ImageInCopyIn
from base.sensitive import COSTS

ProductType = Literal["physical", "service"]
ProductStatus = Literal["active", "inactive", "needs_tax_setup", "sold_out"]
ProductSort = Literal[
    "name",
    "-name",
    "sku",
    "-sku",
    "price",
    "-price",
    "stock",
    "-stock",
    "created_at",
    "-created_at",
]

#: What a product costs the business, as a product reads: only whoever sees the costs gets it (base.sensitive).
ProductCost = Annotated[
    int | None,
    Field(description="Cost in cents; null for whoever does not see the costs.", json_schema_extra={"money": True, **COSTS}),
]
Name = _text(200, 1)
Sku = _text(64, 1)
Ean13 = _text(13)


class ProductSoldOutIn(ProductRefIn):
    sold_out: bool = Field(
        title=gettext_noop("Sold out"),
        description="True: sold out («86»), the till stops offering it; false: back on sale."
    )


class ProductIdIn(Schema):
    """A product by its id alone: the one a deleted product keeps (INVENTORY-F34), the same in a separate copy of the
    business and in the business."""

    id: UUID = Field(title=T_PRODUCT, description="The product's id.")


class ProductRestoreIn(ProductIdIn, ImageInCopyIn):
    """A deleted product of a separate copy the business still holds, by its id, and the image it showed there: one
    deleted before deleting kept the image of the library gets it back."""


class ProductFiltersIn(Schema):
    """The product list's search, filters and order; the export takes the same."""

    search: ProductSearch = None
    name: str | None = Field(None, max_length=200, description="Part of the name.")
    sku: str | None = Field(None, max_length=64, description="Part of the SKU.")
    price_min: Cents | None = Field(None, description="Lowest price, in cents.")
    price_max: Cents | None = Field(None, description="Highest price, in cents.")
    stock_min: Quantity | None = Field(None, description="Lowest stock.")
    stock_max: Quantity | None = Field(None, description="Highest stock.")
    status: ProductStatus | None = Field(
        None,
        description="active or inactive (with a tax category), needs_tax_setup (no tax category: cannot be sold), "
        "or sold_out (marked sold out: the till does not offer it).",
    )
    is_active: bool | None = Field(
        None,
        description="Only the products on sale in the till (true: active and not sold out) or the rest "
        "(false: inactive or sold out); with include_sold_out, the active switch alone.",
    )
    include_sold_out: bool = Field(
        False,
        description="With is_active: filter by the active switch alone, sold out or not (screens that "
        "configure rather than sell, such as a menu's choices).",
    )
    needs_tax_setup: bool | None = Field(
        None, description="Only products without (true) or with (false) a tax category."
    )
    tracks_stock: bool | None = Field(
        None,
        description="Only products whose stock is (true) or is not (false) tracked.",
    )
    category_id: UUID | None = Field(
        None, description="Only the products of this category."
    )
    category: str | None = Field(
        None,
        max_length=200,
        description="Only the products of the category with this name or slug.",
    )
    product_type: ProductType | None = Field(None, description="physical or service.")
    sort: ProductSort = Field("name", description="Order; a leading '-' reverses it.")


class ProductListIn(PageIn, ProductFiltersIn):
    pass


class ForSaleListIn(PageIn):
    search: ProductSearch = None


class ProductIn(AllergensIn):
    name: Name = Field(
        description="The product's name, as the till and the ticket show it."
    )
    sku: Sku = Field(
        description="The product's code; its identity, never edited afterwards."
    )
    price: Cents = Field(
        description="Sale price in cents, per price_quantity of pricing_unit."
    )
    tax_category_key: TaxKey = Field(
        title=TAX_CATEGORY,
        description="Key of the tax category (Taxes app) that says how it is taxed.",
        json_schema_extra=A_TAX_CATEGORY,
    )
    cost: Cents = Field(0, description="Cost in cents; only whoever sees the costs sends one.", json_schema_extra=COSTS)
    initial_stock: Quantity = Field(
        Decimal("0"),
        ge=0,
        title=gettext_noop("Initial stock"),
        description="Stock it starts with; it leaves an 'initial' movement.",
    )
    low_stock_threshold: Quantity | None = Field(
        None,
        ge=0,
        description="Low-stock threshold; null takes the business's default from the settings.",
    )
    ean13: Ean13 | None = Field(None, description="Its EAN-13 barcode, if it has one.")
    description: Description = Field("", description="Free description.")
    product_type: ProductType = Field(
        "physical", description="physical (has stock) or service (never has stock)."
    )
    unit: UnitCode = Field(
        "ud", description="Unit of measure of its stock and of its quantities."
    )
    price_quantity: Quantity = Field(
        Decimal("1"),
        gt=0,
        description="The price is per this quantity (e.g. 100 for 'per 100 g').",
    )
    pricing_unit: UnitCode | None = Field(
        None, description="The unit the price refers to; null = the product's unit."
    )
    track_stock: bool | None = Field(
        None,
        description="Whether its stock is tracked; null follows the business's setting.",
    )
    category_ids: list[Annotated[UUID, Field(json_schema_extra=A_CATEGORY)]] = Field(
        default_factory=list,
        max_length=MAX_BATCH,
        title=CATEGORIES,
        description="Categories that group it in the till.",
    )
    is_active: bool = Field(
        True, description="Whether it is on sale; one created inactive stays out of the till until it is activated."
    )


class ProductRecoverIn(ProductIn, ImageInCopyIn):
    """A product of a separate copy the business no longer holds: what ``inventory.product.create`` takes and the image
    it showed there (the business makes its own id)."""


class ProductPatchIn(ProductRefIn, AllergensPatchIn):
    """Only the fields sent are changed; ``null`` leaves one as it is; ``ean13: ""`` clears it.

    The SKU (the product's identity), the type and the stock are not editable: sending them is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = Field(None, description="New name.")
    price: Cents | None = Field(None, description="New price in cents.")
    cost: Cents | None = Field(
        None, description="New cost in cents; only whoever sees the costs sends one.", json_schema_extra=COSTS
    )
    low_stock_threshold: Quantity | None = Field(
        None, ge=0, description="New low-stock threshold."
    )
    ean13: Ean13 | None = Field(
        None, description="New EAN-13; an empty text removes it."
    )
    description: Description | None = Field(None, description="New description.")
    tax_category_key: TaxKey | None = Field(
        None, title=TAX_CATEGORY, description="Key of the new tax category; it cannot be emptied.", json_schema_extra=A_TAX_CATEGORY
    )
    is_active: bool | None = Field(
        None, description="Activate (true) or deactivate (false) it."
    )
    unit: UnitCode | None = Field(
        None, description="New unit of measure; only while its stock is zero."
    )
    price_quantity: Quantity | None = Field(
        None, gt=0, description="New quantity the price refers to."
    )
    pricing_unit: UnitCode | None = Field(
        None, description="New unit the price refers to."
    )
    track_stock: bool | None = Field(
        None, description="Track (true) or stop tracking (false) its stock."
    )
    category_ids: list[Annotated[UUID, Field(json_schema_extra=A_CATEGORY)]] | None = Field(
        None,
        max_length=MAX_BATCH,
        title=CATEGORIES,
        description="Its categories, all of them: replaces the ones it had.",
    )


class ProductOut(AllergensOut):
    id: UUID = Field(description="The product's id.")
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU, its identity.")
    ean13: str | None = Field(description="EAN-13 barcode.")
    description: str = Field(description="Description.")
    product_type: ProductType = Field(description="physical or service.")
    price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit.", json_schema_extra={"money": True}
    )
    cost: ProductCost
    stock: Decimal = Field(description="Current stock, in its unit.")
    low_stock_threshold: Decimal = Field(description="Low-stock threshold.")
    unit: UnitCode = Field(description="Unit of measure.")
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: UnitCode = Field(description="Unit the price refers to.")
    tax_category_id: UUID | None = Field(description="Its tax category.")
    tax_category_key: str | None = Field(description="Key of its tax category.")
    needs_tax_setup: bool = Field(
        description="True: no tax category, it cannot be sold until it has one."
    )
    track_stock: bool | None = Field(
        description="Its own decision on stock control; null follows the business."
    )
    tracks_stock: bool = Field(description="Whether stock control applies to it now.")
    is_active: bool = Field(description="Active: sold in the till, unless it is sold out.")
    is_sold_out: bool = Field(
        description="Sold out («86»): still active, but the till does not offer it until it is back on sale."
    )
    category_ids: list[UUID] = Field(description="Its categories.")
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")


ProductPage = Page[ProductOut]


class ProductsOut(Schema):
    rows: list[ProductOut] = Field(description="The products, as they are now.")


class SaleProductOut(AllergensOut):
    """What the till needs to price and sell a product; never its stock."""

    id: UUID = Field(description="The product's id.")
    name: str = Field(description="Name, as the ticket and the kitchen read it.")
    sku: str = Field(description="SKU.")
    product_type: ProductType = Field(description="physical or service.")
    price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit.", json_schema_extra={"money": True}
    )
    cost: ProductCost
    tax_category_id: UUID | None = Field(description="Its tax category.")
    tax_category_key: str | None = Field(description="Key of its tax category.")
    needs_tax_setup: bool = Field(
        description="True: it cannot be sold until it has a tax category."
    )
    unit: UnitCode = Field(description="Unit of measure.")
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: UnitCode = Field(description="Unit the price refers to.")
    tracks_stock: bool = Field(description="Whether a sale lowers its stock.")
    image: str = Field(
        description="Its image: catalog:<folder>/<name> of the shared library, file:<name> of a photo of its own, "
        "or empty."
    )
    image_url: str = Field(description="Where the Hub serves its image; empty: it has none (show its initials).")


SaleProductPage = Page[SaleProductOut]
