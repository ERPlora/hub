"""Schemas of the tables of the room (``table.table.*``): naming one, the list, creating one or many, editing one
and moving it on the plan. What the live floor answers of each table is in ``floor``."""

from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field
from pydantic import model_validator

from apps.table.models import (
    BOX,
    MAX_CAPACITY,
    MAX_PLAN,
    MIN_BOX,
)
from apps.table.schemas.fields import (
    A_TABLE,
    A_ZONE,
    MOVE_TO_ZONE,
    SAY_WHICH_TABLE,
    SAY_WHICH_ZONE,
    TABLE,
    In,
    PageIn,
    Said,
    Shape,
    TableStatus,
    _named,
    _text,
)

#: The most tables one bulk create makes (the old module's 100).
MAX_BULK = 100

TableSort = Literal[
    "number",
    "-number",
    "name",
    "-name",
    "zone_name",
    "-zone_name",
    "capacity",
    "-capacity",
    "status",
    "-status",
]


Number = _text(20, 1)
Seats = Annotated[int, Field(ge=1, le=MAX_CAPACITY)]
Coordinate = Annotated[int, Field(ge=0, le=MAX_PLAN)]
Side = Annotated[int, Field(ge=MIN_BOX, le=MAX_PLAN)]


class TableRefIn(In):
    id: UUID | None = Field(None, title=TABLE, description="The table's id.", json_schema_extra=A_TABLE)
    table: Said | None = Field(
        None,
        description="The table's number (or its name), when its id is not known, e.g. «4».",
    )
    zone: Said | None = Field(
        None,
        description="The name of the table's zone, when the same number is in several zones.",
    )

    @model_validator(mode="after")
    def _said(self):
        _named(self.id, self.table, SAY_WHICH_TABLE)
        return self


class TableListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the table's number or name."
    )
    number: str | None = Field(
        None, max_length=20, description="Part of the table's number."
    )
    name: str | None = Field(
        None, max_length=100, description="Part of the table's name."
    )
    zone_id: UUID | None = Field(None, description="Only the tables of this zone.")
    zone: str | None = Field(
        None, max_length=100, description="Only the tables of the zone with this name."
    )
    status: TableStatus | None = Field(
        None,
        description="Only the tables available, occupied, reserved or blocked right now.",
    )
    shape: Shape | None = Field(None, description="Only the tables of this shape.")
    is_active: bool | None = Field(
        None, description="Only the tables in use (true) or out of use (false)."
    )
    in_service: bool | None = Field(
        None,
        description="Only the tables that serve (active, in an active zone): the service view's.",
    )
    capacity_min: int | None = Field(None, ge=0, description="Fewest seats.")
    capacity_max: int | None = Field(None, ge=0, description="Most seats.")
    sort: TableSort = Field(
        "number",
        description="Order (numbers in natural order); a leading '-' reverses it.",
    )


class TableIn(In):
    zone_id: UUID | None = Field(None, description="The zone it goes in.", json_schema_extra=A_ZONE)
    zone: Said | None = Field(
        None, description="The name of the zone it goes in, when its id is not known."
    )
    number: Number | None = Field(
        None,
        description="Its number or name (S1, Terrace A); empty = the first free number of the zone.",
    )
    name: _text(100) = Field("", description="An optional name.")
    capacity: Seats = Field(4, description="Seats.")
    shape: Shape = Field("square", description="square, round or rectangle.")
    position_x: Coordinate | None = Field(
        None, description="Where on the plan (pixels); empty = the first free spot."
    )
    position_y: Coordinate | None = Field(
        None, description="Where on the plan (pixels); empty = the first free spot."
    )
    width: Side | None = Field(
        None, description=f"Its box on the plan, in pixels ({BOX} by default)."
    )
    height: Side | None = Field(
        None, description=f"Its box on the plan, in pixels ({BOX} by default)."
    )


class TableBulkIn(In):
    zone_id: UUID | None = Field(None, description="The zone they go in.", json_schema_extra=A_ZONE)
    zone: Said | None = Field(
        None, description="The name of the zone they go in, when its id is not known."
    )
    count: int = Field(
        ge=1, le=MAX_BULK, description=f"How many tables (1 to {MAX_BULK})."
    )
    prefix: _text(10) = Field(
        "",
        title=gettext_noop("Number prefix"),
        description="What goes before each number, e.g. T for T1, T2…",
    )
    start_number: int = Field(
        1,
        ge=0,
        le=100_000,
        title=gettext_noop("First number"),
        description="The first number.",
    )
    capacity: Seats = Field(4, description="Seats of each one.")
    shape: Shape = Field("square", description="square, round or rectangle.")

    @model_validator(mode="after")
    def _said(self):
        _named(self.zone_id, self.zone, SAY_WHICH_ZONE)
        return self


class TablePatchIn(TableRefIn):
    number: Number | None = Field(None, description="The new number.")
    name: _text(100) | None = Field(
        None, description="The new name (empty removes it)."
    )
    capacity: Seats | None = Field(None, description="The new seats.")
    shape: Shape | None = Field(None, description="The new shape.")
    move_to_zone_id: UUID | None = Field(
        None, title=MOVE_TO_ZONE, description="The zone it moves to.", json_schema_extra=A_ZONE
    )
    move_to_zone: Said | None = Field(
        None, title=MOVE_TO_ZONE, description="The name of the zone it moves to."
    )
    blocked: bool | None = Field(
        None,
        description="Out of service (true: nobody is seated there) or back in service (false).",
    )
    is_active: bool | None = Field(
        None, description="In use (true) or out of use (false)."
    )


class TableMoveIn(In):
    id: UUID = Field(title=TABLE, description="The table's id.", json_schema_extra=A_TABLE)
    position_x: Coordinate = Field(description="Left edge on the plan, in pixels.")
    position_y: Coordinate = Field(description="Top edge on the plan, in pixels.")
    width: Side | None = Field(
        None, description="Its box's width, in pixels; empty keeps it."
    )
    height: Side | None = Field(
        None, description="Its box's height, in pixels; empty keeps it."
    )
