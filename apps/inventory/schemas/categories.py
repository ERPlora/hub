"""Schemas of the categories: their list and filters, create, edit and recover, and how a category reads."""

from typing import Annotated, Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints

from apps.inventory.schemas.fields import MAX_BATCH, TAX_RATE, CategoryRefIn, Description, Page, PageIn, TaxKey, _text

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
        None, ge=0, description="At least this many active products, sold out included."
    )
    product_count_max: int | None = Field(
        None, ge=0, description="At most this many active products, sold out included."
    )
    sort: CategorySort = Field("name", description="Order; a leading '-' reverses it.")


class CategoryListIn(PageIn, CategoryFiltersIn):
    ids: list[UUID] | None = Field(
        None,
        max_length=MAX_BATCH,
        description="Only these categories, by id (to name the categories of a product).",
    )


class CategoryIn(Schema):
    name: CategoryName = Field(
        description="The category's name. Before creating one, look at the ones there are (inventory.category.list): "
        "they may be written in another language («Desserts» for «postres»); if one is the same, ask."
    )
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
        None, title=TAX_RATE, description="Key of a tax category (Taxes app), optional."
    )


class CategoryRecoverIn(CategoryIn):
    product_ids: list[UUID] = Field(
        default_factory=list,
        max_length=10_000,
        description="Deleted products to put back in it, so that they come back inside it when restored.",
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
        None, title=TAX_RATE, description="Key of the new tax category; an empty text removes it."
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
    product_count: int = Field(description="Active products in it, sold out included (what the till shows).")


CategoryPage = Page[CategoryOut]
