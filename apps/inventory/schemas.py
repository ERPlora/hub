"""Input and output schemas of the inventory app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in cents (integers, never negative); quantities as exact decimals with at most three places (the
finest step of any unit: a gram in a kilo); the step of each product's unit is checked by the
operations. A product or a category is named by its id or, as a person says it (assistant, voice),
by its SKU or name (``product``) or its name or slug (``category``).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, model_validator

T = TypeVar("T")

#: Ninety-nine billion euros in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Rows of one bulk create (CSV import) or lines of one reception.
MAX_BATCH = 100

SAY_WHICH_PRODUCT = _("Say which product: its id, or its SKU or name.")
SAY_WHICH_CATEGORY = _("Say which category: its id, or its name.")

UnitCode = Literal["ud", "kg", "g", "t", "l", "ml", "min", "h"]
ProductType = Literal["physical", "service"]
MovementType = Literal["initial", "reception", "sale", "void", "count", "write_off", "refund"]
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
CategorySort = Literal[
    "name",
    "-name",
    "slug",
    "-slug",
    "icon",
    "-icon",
    "color",
    "-color",
    "product_count",
    "-product_count",
]
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
ImportStatus = Literal["ready", "created", "skipped", "failed"]


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(200, 1)
Sku = _text(64, 1)
Ean13 = _text(13)
TaxKey = _text(64, 1)
Description = Annotated[str, StringConstraints(max_length=2000)]
Reason = _text(500, 3)
CategoryName = _text(100, 1)
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$|^$"
    ),
]
Color = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^#[0-9a-fA-F]{6}$|^$")
]
Icon = _text(64)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS)]
Quantity = Annotated[Decimal, Field(max_digits=15, decimal_places=3)]
#: How a person names a product (its SKU or name) or a category (its name or slug).
Said = _text(200, 1)
#: A raw CSV cell, as typed in the file.
Cell = _text(500)


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
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


# References: by id, or as a person says it


class ProductRefIn(Schema):
    id: UUID | None = Field(None, description="The product's id.")
    product: Said | None = Field(
        None,
        description="The product's SKU or name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


class ProductSoldOutIn(ProductRefIn):
    sold_out: bool = Field(
        description="True: sold out («86»), the till stops offering it; false: back on sale."
    )


class CategoryRefIn(Schema):
    id: UUID | None = Field(None, description="The category's id.")
    category: Said | None = Field(
        None, description="The category's name or slug, when its id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


class _ProductLineRef(Schema):
    """A product named by ``product_id`` or by its SKU or name (``product``)."""

    product_id: UUID | None = Field(None, description="The product's id.")
    product: Said | None = Field(
        None,
        description="The product's SKU or name, when its id is not known (e.g. said aloud).",
    )

    @model_validator(mode="after")
    def _named(self):
        if self.product_id is None and self.product is None:
            raise ValueError(str(SAY_WHICH_PRODUCT))
        return self


# Inputs: lists


class ProductFiltersIn(Schema):
    """The product list's search, filters and order; the export takes the same."""

    search: str | None = Field(
        None, max_length=200, description="Part of the name or the SKU."
    )
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
        "(false: inactive or sold out).",
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


class LowStockListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Part of the name or the SKU."
    )
    sku: str | None = Field(None, max_length=64, description="This exact SKU.")
    stock_min: Quantity | None = Field(None, description="Lowest stock.")
    stock_max: Quantity | None = Field(None, description="Highest stock.")
    sort: LowStockSort = Field(
        "stock",
        description="Order (the one with less first by default); a leading '-' reverses it.",
    )


class ForSaleListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Part of the name or the SKU."
    )


class ProductCategoryListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Part of the product's name or SKU, or of the category's name.",
    )
    product_id: UUID | None = Field(
        None, description="Only the categories of this product."
    )
    category_id: UUID | None = Field(
        None, description="Only the products of this category."
    )


class CategoryFiltersIn(Schema):
    search: str | None = Field(
        None, max_length=100, description="Part of the name or the slug."
    )
    name: str | None = Field(None, max_length=100, description="Part of the name.")
    slug: str | None = Field(None, max_length=120, description="Part of the slug.")
    icon: str | None = Field(None, max_length=64, description="This exact icon.")
    color: str | None = Field(
        None, max_length=7, description="This exact colour (#rrggbb)."
    )
    product_count_min: int | None = Field(
        None, ge=0, description="At least this many products on sale (active, not sold out)."
    )
    product_count_max: int | None = Field(
        None, ge=0, description="At most this many products on sale (active, not sold out)."
    )
    sort: CategorySort = Field("name", description="Order; a leading '-' reverses it.")


class CategoryListIn(PageIn, CategoryFiltersIn):
    pass


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


class UnitListIn(PageIn):
    search: str | None = Field(
        None, max_length=50, description="Part of the code or the name of the unit."
    )


class SummaryIn(Schema):
    pass


class ConfigGetIn(Schema):
    pass


# Inputs: products


class ProductIn(Schema):
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
        description="Key of the tax category (Taxes app) that says how it is taxed."
    )
    cost: Cents = Field(0, description="Cost in cents.")
    initial_stock: Quantity = Field(
        Decimal("0"),
        ge=0,
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
    category_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_BATCH,
        description="Categories that group it in the till.",
    )


class ProductPatchIn(ProductRefIn):
    """Only the fields sent are changed; ``null`` leaves one as it is; ``ean13: ""`` clears it.

    The SKU (the product's identity), the type and the stock are not editable: sending them is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name | None = Field(None, description="New name.")
    price: Cents | None = Field(None, description="New price in cents.")
    cost: Cents | None = Field(None, description="New cost in cents.")
    low_stock_threshold: Quantity | None = Field(
        None, ge=0, description="New low-stock threshold."
    )
    ean13: Ean13 | None = Field(
        None, description="New EAN-13; an empty text removes it."
    )
    description: Description | None = Field(None, description="New description.")
    tax_category_key: TaxKey | None = Field(
        None, description="Key of the new tax category; it cannot be emptied."
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
    category_ids: list[UUID] | None = Field(
        None,
        max_length=MAX_BATCH,
        description="Its categories, all of them: replaces the ones it had.",
    )


class ProductImportRowIn(Schema):
    """One row of a CSV, its columns already mapped to our fields, each cell as written in the file."""

    line: int = Field(ge=1, description="Line of the file, for the report.")
    name: Cell = Field("", description="Name cell.")
    sku: Cell = Field("", description="SKU cell.")
    price: Cell = Field(
        "", description="Price cell, as written (2,20 · 1.234,56 · 2.20 €)."
    )
    cost: Cell = Field("", description="Cost cell, as written.")
    stock: Cell = Field("", description="Stock cell, as written.")
    low_stock_threshold: Cell = Field(
        "",
        description="Threshold cell, as written; empty takes the business's default.",
    )
    ean13: Cell = Field("", description="EAN-13 cell.")
    description: Annotated[str, StringConstraints(max_length=2000)] = Field(
        "", description="Description cell."
    )
    unit: Cell = Field(
        "", description="Unit cell (ud, kg, g, t, l, ml, min, h); empty = ud."
    )
    tax_category_key: Cell = Field(
        "", description="Key of the tax category chosen for this row's fiscal text."
    )


class ProductImportIn(Schema):
    rows: list[ProductImportRowIn] = Field(
        min_length=1,
        max_length=MAX_BATCH,
        description="The rows, at most 100 per call.",
    )
    dry_run: bool = Field(
        False,
        description="True rehearses: every row is checked and reported, nothing is created.",
    )


class ProductCategoryIn(_ProductLineRef):
    category_id: UUID | None = Field(None, description="The category's id.")
    category: Said | None = Field(
        None, description="The category's name or slug, when its id is not known."
    )

    @model_validator(mode="after")
    def _category_named(self):
        if self.category_id is None and self.category is None:
            raise ValueError(str(SAY_WHICH_CATEGORY))
        return self


# Inputs: categories


class CategoryIn(Schema):
    name: CategoryName = Field(description="The category's name.")
    slug: Slug = Field(
        "", description="Lowercase with dashes; empty = made from the name."
    )
    description: Description = Field("", description="Free description.")
    icon: Icon = Field(
        "ion:cube-outline", description="Iconify icon (e.g. ion:wine-outline) for the till's strip."
    )
    color: Color = Field("#3880ff", description="Colour #rrggbb for the till's strip.")
    order: int = Field(
        0, ge=0, le=1_000_000, description="Position among the categories."
    )
    tax_category_key: TaxKey | None = Field(
        None, description="Key of a tax category (Taxes app), optional."
    )


class CategoryPatchIn(CategoryRefIn):
    """Only the fields sent are changed; ``tax_category_key: ""`` clears it. A category is not deactivated."""

    model_config = ConfigDict(extra="forbid")

    name: CategoryName | None = Field(None, description="New name.")
    slug: Slug | None = Field(None, description="New slug.")
    description: Description | None = Field(None, description="New description.")
    icon: Icon | None = Field(None, description="New icon.")
    color: Color | None = Field(None, description="New colour.")
    order: int | None = Field(None, ge=0, le=1_000_000, description="New position.")
    tax_category_key: _text(64) | None = Field(
        None, description="Key of the new tax category; an empty text removes it."
    )


class CategoryImportRowIn(Schema):
    line: int = Field(ge=1, description="Line of the file, for the report.")
    name: Cell = Field("", description="Name cell.")
    slug: Cell = Field("", description="Slug cell; empty = made from the name.")
    tax_category_key: Cell = Field(
        "",
        description="Fiscal text of the file: a tax category's key, name or learned alias.",
    )


class CategoryImportIn(Schema):
    rows: list[CategoryImportRowIn] = Field(
        min_length=1,
        max_length=MAX_BATCH,
        description="The rows, at most 100 per call.",
    )


# Inputs: stock


class ReceiveLineIn(_ProductLineRef):
    qty: Quantity = Field(gt=0, description="Quantity received, in the product's unit.")
    unit_cost: Cents | None = Field(
        None, description="Cost per unit in cents; null keeps the cost the product had."
    )


class ReceiveIn(Schema):
    items: list[ReceiveLineIn] = Field(
        min_length=1, max_length=MAX_BATCH, description="The products received."
    )
    reference: _text(200) = Field("", description="The delivery note's number.")


class CountIn(_ProductLineRef):
    stock: Quantity = Field(
        ge=0, description="What there really is: the total counted, not the difference."
    )
    reason: Reason = Field(description="Why (3 to 500 characters).")


class WriteOffIn(_ProductLineRef):
    qty: Quantity = Field(
        gt=0, description="Quantity written off, in the product's unit."
    )
    reason: Reason = Field(
        description="Why: waste, breakage, own consumption… (3 to 500 characters)."
    )


class ConfigPatchIn(Schema):
    allow_sell_without_stock: bool | None = Field(
        None,
        description="True: a sale lowers the stock even below zero. False: an article that does not reach is not lowered.",
    )
    low_stock_threshold: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Whole units: the threshold of a product created without its own.",
    )
    track_stock: bool | None = Field(
        None, description="Whether articles that did not decide track their stock."
    )


# Inputs: events of other apps (events.py)


class SaleComponentIn(Schema):
    product_id: UUID | None = Field(None, description="The component's product.")
    quantity: Quantity = Field(
        Decimal("0"),
        description="Quantity of it sold in the line, the line's multiplier applied.",
    )
    is_service: bool = Field(False, description="A service never moves stock.")


class SaleItemIn(Schema):
    product_id: UUID | None = Field(
        None, description="The line's product; none for a free-price line."
    )
    quantity: Quantity = Field(Decimal("0"), description="Quantity sold.")
    is_service: bool = Field(False, description="A service never moves stock.")
    components: list[SaleComponentIn] = Field(
        default_factory=list,
        description="A menu or a pack: it has no stock, its components move instead.",
    )


class SaleCompletedIn(Schema):
    sale_id: UUID = Field(description="The sale that was paid.")
    items: list[SaleItemIn] = Field(default_factory=list, description="Its lines.")


class SaleVoidedIn(Schema):
    sale_id: UUID = Field(description="The sale that was voided.")


class SaleRefundLineIn(Schema):
    product_id: UUID | None = Field(None, description="The returned line's product; none for a free-price line.")
    quantity: Quantity = Field(Decimal("0"), description="How many units of it come back.")


class SaleRefundedIn(Schema):
    """What inventory reads of Sales' ``sale.sale.refunded``; the rest of the payload is ignored."""

    sale_id: UUID = Field(description="The sale refunded.")
    refund_id: UUID = Field(description="The refund: each one gives its units back once.")
    reason: _text(500) = Field("", description="Why it was refunded; it goes on the movement.")
    lines: list[SaleRefundLineIn] = Field(
        default_factory=list, description="The lines that come back; none = only money."
    )


# Outputs


class ProductOut(Schema):
    id: UUID = Field(description="The product's id.")
    name: str = Field(description="Name.")
    sku: str = Field(description="SKU, its identity.")
    ean13: str | None = Field(description="EAN-13 barcode.")
    description: str = Field(description="Description.")
    product_type: ProductType = Field(description="physical or service.")
    price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit."
    )
    cost: int = Field(description="Cost in cents.")
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
    created_at: datetime = Field(description="When it was created.")
    updated_at: datetime = Field(description="When it last changed.")


ProductPage = Page[ProductOut]


class ProductsOut(Schema):
    rows: list[ProductOut] = Field(description="The products, as they are now.")


class SaleProductOut(Schema):
    """What the till needs to price and sell a product; never its stock."""

    id: UUID = Field(description="The product's id.")
    name: str = Field(description="Name, as the ticket and the kitchen read it.")
    sku: str = Field(description="SKU.")
    product_type: ProductType = Field(description="physical or service.")
    price: int = Field(
        description="Price in cents, per price_quantity of pricing_unit."
    )
    cost: int = Field(description="Cost in cents.")
    tax_category_id: UUID | None = Field(description="Its tax category.")
    tax_category_key: str | None = Field(description="Key of its tax category.")
    needs_tax_setup: bool = Field(
        description="True: it cannot be sold until it has a tax category."
    )
    unit: UnitCode = Field(description="Unit of measure.")
    price_quantity: Decimal = Field(description="Quantity the price refers to.")
    pricing_unit: UnitCode = Field(description="Unit the price refers to.")
    tracks_stock: bool = Field(description="Whether a sale lowers its stock.")


SaleProductPage = Page[SaleProductOut]


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


class ProductCategoryOut(Schema):
    product_id: UUID = Field(description="The product.")
    category_id: UUID = Field(description="One of its categories.")


ProductCategoryPage = Page[ProductCategoryOut]


class ProductCategoryLinkOut(ProductCategoryOut):
    changed: bool = Field(
        description="False when nothing changed (the link was already there, or was not)."
    )


class CategoryOut(Schema):
    id: UUID = Field(description="The category's id.")
    name: str = Field(description="Name.")
    slug: str = Field(description="Slug.")
    description: str = Field(description="Description.")
    icon: str = Field(description="Icon.")
    color: str = Field(description="Colour.")
    order: int = Field(description="Position.")
    tax_category_id: UUID | None = Field(description="Its tax category, if any.")
    tax_category_key: str | None = Field(description="Key of its tax category, if any.")
    product_count: int = Field(description="Products on sale in it (active, not sold out).")


CategoryPage = Page[CategoryOut]


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
    unit_cost: int | None = Field(description="Cost per unit in cents (receptions).")
    actor: str = Field(description="Who made it.")
    created_at: datetime = Field(description="When.")


MovementPage = Page[MovementOut]


class SummaryOut(Schema):
    products_tracked: int = Field(description="Active articles with stock control.")
    products_in_stock: int = Field(description="Of them, with stock above zero.")
    products_out_of_stock: int = Field(description="Of them, at zero or below.")
    products_low_stock: int = Field(description="Of them, at or under their threshold.")
    products_without_cost: int = Field(
        description="Of them, without a cost: the value is partial."
    )
    stock_value: int = Field(
        description="Σ cost × stock of the ones in stock, in cents."
    )
    active_products: int = Field(description="Every active product, services included.")


class UnitOut(Schema):
    code: UnitCode = Field(description="Code.")
    name: str = Field(description="Name, in the request's language.")
    category: str = Field(description="count, mass, volume or time.")
    factor_num: int = Field(
        description="Numerator of the exact factor towards the reference unit of its category."
    )
    factor_den: int = Field(description="Denominator of that factor (1 min = 1/60 h).")
    increment: Decimal = Field(
        description="The step every quantity in this unit is a multiple of."
    )
    is_reference: bool = Field(
        description="Whether it is the reference unit of its category."
    )


UnitPage = Page[UnitOut]


class ConfigOut(Schema):
    allow_sell_without_stock: bool = Field(
        description="Whether a sale lowers the stock below zero."
    )
    low_stock_threshold: int = Field(
        description="Default threshold of a new product, in whole units."
    )
    track_stock: bool = Field(
        description="Whether articles that did not decide track their stock."
    )


class ImportRowOut(Schema):
    line: int = Field(description="Line of the file.")
    key: str = Field(description="The row's SKU (products) or name (categories).")
    status: ImportStatus = Field(
        description="ready (rehearsal), created, skipped (already existed) or failed."
    )
    id: UUID | None = Field(None, description="What it created.")
    reason: str = Field("", description="Why it failed.")


class ImportReportOut(Schema):
    dry_run: bool = Field(description="True: a rehearsal, nothing was created.")
    total: int = Field(description="Rows.")
    ready: int = Field(description="Rows that would be created (rehearsal).")
    created: int = Field(description="Rows created.")
    skipped: int = Field(description="Rows skipped because they already existed.")
    failed: int = Field(description="Rows that failed.")
    rows: list[ImportRowOut] = Field(description="Each row with its outcome.")


class ExportOut(Schema):
    filename: str = Field(description="Name of the file.")
    content_type: str = Field(description="Media type.")
    content: str = Field(description="The CSV.")


class SaleStockOut(Schema):
    sale_id: UUID = Field(description="The sale.")
    state: str = Field(description="moved, unmoved (nothing to move) or voided.")
    applied: bool = Field(
        description="False: it had been applied already, nothing was done this time."
    )
    movements: int = Field(description="Movements written this time.")


class RefundStockOut(Schema):
    refund_id: UUID = Field(description="The refund.")
    sale_id: UUID = Field(description="Its sale.")
    applied: bool = Field(
        description="False: it had been applied already, nothing was done this time."
    )
    movements: int = Field(description="Movements written this time.")


class DeletedOut(Schema):
    id: UUID = Field(description="What was deleted.")
