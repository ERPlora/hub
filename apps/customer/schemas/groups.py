"""Schemas of the customer groups."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.fields import GROUP_COLOR, INT4_MAX, GroupRefIn, Page, PageIn, _text


class GroupListIn(PageIn):
    search: str | None = Field(
        None,
        max_length=200,
        description="Text to look for in the name and description.",
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) groups."
    )
    color: str | None = Field(
        None, max_length=20, description="Only groups of this color."
    )
    customers_min: int | None = Field(
        None, ge=0, description="Only groups with at least this many customers."
    )
    customers_max: int | None = Field(
        None, ge=0, description="Only groups with at most this many customers."
    )
    sort: Literal[
        "name", "description", "color", "sort_order", "is_active", "customer_count"
    ] = Field("name", description="The column to order by; the id breaks ties.")
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


class GroupIn(Schema):
    name: _text(100, 1) = Field(
        description="The group's name, unique among the active groups."
    )
    description: _text(1000) = Field("", description="What the group is for.")
    color: _text(20, 1) = Field(
        "primary", title=GROUP_COLOR, description="The group's color, a name of the theme (primary)."
    )
    sort_order: int = Field(0, ge=0, le=INT4_MAX, description="Its place in the lists, lowest first.")


class GroupPatchIn(GroupRefIn):
    name: _text(100, 1) | None = Field(None, description="The new name.")
    description: _text(1000) | None = Field(None, description="The new description.")
    color: _text(20, 1) | None = Field(None, title=GROUP_COLOR, description="The new color.")
    sort_order: int | None = Field(None, ge=0, le=INT4_MAX, description="The new place in the lists.")
    is_active: bool | None = Field(
        None, description="Whether the group is offered on the cards."
    )


class GroupRow(Schema):
    id: UUID = Field(description="The group's id.")
    name: str = Field(description="Name.")
    description: str = Field(description="Description.")
    color: str = Field(description="Color.")
    sort_order: int = Field(description="Place in the lists.")
    is_active: bool = Field(description="Whether it is offered on the cards.")
    customer_count: int = Field(description="How many customers are in it.")


GroupPage = Page[GroupRow]
