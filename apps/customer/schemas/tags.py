"""Schemas of the customer tags."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.customer.schemas.fields import TAG_COLOR, Page, PageIn, TagRefIn, _text


class TagListIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the name."
    )
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) tags."
    )
    color: str | None = Field(
        None, max_length=20, description="Only tags of this color."
    )
    sort: Literal["name", "color", "is_active", "customer_count"] = Field(
        "name", description="The column to order by; the id breaks ties."
    )
    descending: bool = Field(
        False, description="Order from the highest to the lowest (Z to A)."
    )


class TagIn(Schema):
    name: _text(60, 1) = Field(
        description="The tag's name, unique among the active tags."
    )
    color: _text(20, 1) = Field(
        "primary", title=TAG_COLOR, description="The tag's color, a name of the theme (primary)."
    )


class TagPatchIn(TagRefIn):
    name: _text(60, 1) | None = Field(None, description="The new name.")
    color: _text(20, 1) | None = Field(None, title=TAG_COLOR, description="The new color.")
    is_active: bool | None = Field(
        None, description="Whether the tag is offered on the cards."
    )


class TagRow(Schema):
    id: UUID = Field(description="The tag's id.")
    name: str = Field(description="Name.")
    color: str = Field(description="Color.")
    is_active: bool = Field(description="Whether it is offered on the cards.")
    customer_count: int = Field(description="How many customers have it.")


TagPage = Page[TagRow]
