"""Schemas of the zones of the room (``table.zone.*``)."""

from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import model_validator

from apps.table.schemas.fields import (
    A_ZONE,
    SAY_WHICH_ZONE,
    ZONE,
    ZONE_COLOUR,
    In,
    Page,
    PageIn,
    Said,
    _named,
    _text,
)

Color = Literal[
    "primary", "secondary", "tertiary", "success", "warning", "danger", "medium"
]

ZoneSort = Literal[
    "sort_order",
    "-sort_order",
    "name",
    "-name",
    "color",
    "-color",
    "table_count",
    "-table_count",
    "available_count",
    "-available_count",
    "is_active",
    "-is_active",
]


Name = _text(100, 1)
Description = _text(500)


class ZoneRefIn(In):
    id: UUID | None = Field(None, title=ZONE, description="The zone's id.", json_schema_extra=A_ZONE)
    zone: Said | None = Field(
        None, description="The zone's name, when its id is not known (e.g. said aloud)."
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.zone, SAY_WHICH_ZONE)
        return self


class ZoneListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the zone's name."
    )
    name: str | None = Field(
        None, max_length=100, description="Part of the zone's name (the column filter)."
    )
    color: Color | None = Field(None, description="Only the zones of this colour.")
    is_active: bool | None = Field(
        None, description="Only the active (true) or the inactive (false) zones."
    )
    sort: ZoneSort = Field(
        "sort_order", description="Order; a leading '-' reverses it."
    )


class ZoneIn(In):
    name: Name = Field(description="The zone's name, e.g. Dining room, Terrace, Bar.")
    description: Description = Field(
        "", description="Only a description the person asks to put on the zone: empty unless they ask, never written "
        "from what else they say of it (what it is for, who sits there).")
    color: Color = Field(
        "primary", title=ZONE_COLOUR, description="Its colour in the list of zones."
    )
    sort_order: int | None = Field(
        None,
        ge=0,
        le=1_000_000,
        description="Its place among the zones; empty = the last one.",
    )


class ZonePatchIn(ZoneRefIn):
    name: Name | None = Field(None, description="The new name.")
    description: Description | None = Field(None, description="The new description.")
    color: Color | None = Field(None, title=ZONE_COLOUR, description="The new colour.")
    sort_order: int | None = Field(
        None, ge=0, le=1_000_000, description="The new place among the zones."
    )
    is_active: bool | None = Field(
        None,
        description="Active (true) or out of service (false): an inactive zone leaves the service view.",
    )


class ZoneOut(Schema):
    id: UUID = Field(description="The zone's id.")
    name: str = Field(description="Name.")
    description: str = Field(description="Description.")
    color: Color = Field(description="Colour.")
    sort_order: int = Field(description="Place among the zones.")
    is_active: bool = Field(description="Whether it is in service.")
    table_count: int = Field(description="Tables in use in the zone.")
    available_count: int = Field(description="Of them, how many are free right now.")


ZonePage = Page[ZoneOut]
