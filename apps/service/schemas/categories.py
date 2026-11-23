"""Schemas of the service categories."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.service.schemas.fields import (
    A_CATEGORY,
    CategoryRefIn,
    Color,
    Icon,
    In,
    LongText,
    Name,
    Order,
    Page,
    PageIn,
    Said,
)

CategorySort = Literal[
    "sort_order",
    "-sort_order",
    "name",
    "-name",
    "parent_name",
    "-parent_name",
    "service_count",
    "-service_count",
]


class CategoryListIn(PageIn):
    search: str | None = Field(None, max_length=200, description="Part of the name.")
    parent_id: UUID | None = Field(
        None, description="Only the categories inside this one."
    )
    sort: CategorySort = Field(
        "sort_order",
        description="Order (by order, then name); a leading '-' reverses it.",
    )


class CategoryIn(In):
    name: Name = Field(
        description="The category's name; unique among the live ones, ignoring case."
    )
    description: LongText = Field("", description="Free description.")
    parent_id: UUID | None = Field(
        None, description="The category it goes inside, by id; none = a root category.", json_schema_extra=A_CATEGORY
    )
    parent: Said | None = Field(
        None, description="The category it goes inside, by name."
    )
    icon: Icon = Field(
        "", description="An Iconify icon name (ion:cut-outline), or empty."
    )
    color: Color = Field("", description="A colour #rrggbb, or empty.")
    sort_order: Order = Field(0, description="Order in the lists (lowest first).")


class CategoryPatchIn(CategoryRefIn):
    """Only the fields sent change; ``parent_id: null`` makes it a root category."""

    name: Name | None = Field(None, description="New name.")
    description: LongText | None = Field(None, description="New description.")
    parent_id: UUID | None = Field(
        None, description="New parent by id; null makes it a root category.", json_schema_extra=A_CATEGORY
    )
    parent: Said | None = Field(None, description="New parent by name.")
    icon: Icon | None = Field(None, description="New icon.")
    color: Color | None = Field(None, description="New colour.")
    sort_order: Order | None = Field(None, description="New order.")


class CategoryOut(Schema):
    id: UUID
    name: str
    description: str
    parent_id: UUID | None
    parent_name: str | None
    icon: str
    color: str
    sort_order: int
    service_count: int = Field(description="Offered services in it.")
    created_at: datetime
    updated_at: datetime


CategoryPage = Page[CategoryOut]
