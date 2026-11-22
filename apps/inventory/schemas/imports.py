"""Schemas of the CSV import of products and categories, and of its report."""

from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints

from apps.inventory.schemas.fields import FILE_ROWS, MAX_BATCH, _text
from base.allergens import AllergensCellIn
from base.sensitive import COSTS

ImportStatus = Literal["ready", "created", "skipped", "failed"]

#: A raw CSV cell, as typed in the file.
Cell = _text(500)


class ProductImportRowIn(AllergensCellIn):
    """One row of a CSV, its columns already mapped to our fields, each cell as written in the file."""

    line: int = Field(ge=1, description="Line of the file, for the report.")
    name: Cell = Field("", description="Name cell.")
    sku: Cell = Field("", description="SKU cell.")
    price: Cell = Field(
        "", description="Price cell, as written (2,20 · 1.234,56 · 2.20 €)."
    )
    cost: Cell = Field("", description="Cost cell, as written; only whoever sees the costs sends one.", json_schema_extra=COSTS)
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
        title=FILE_ROWS,
        description="The rows, at most 100 per call.",
    )
    dry_run: bool = Field(
        False,
        title=gettext_noop("Check only"),
        description="True rehearses: every row is checked and reported, nothing is created.",
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
        title=FILE_ROWS,
        description="The rows, at most 100 per call.",
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
