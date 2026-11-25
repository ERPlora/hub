"""The stations: their list, one station and its edit."""

from uuid import UUID

from ninja import Field, Schema

from apps.kitchen.schemas.fields import (
    STATION_COLOUR,
    Destination,
    Hex,
    In,
    Page,
    PageIn,
    PrinterUsage,
    StationRefIn,
    StationSort,
    _text,
)


class StationListIn(PageIn):
    search: str | None = Field(None, max_length=120, description="Part of the name.")
    is_active: bool | None = Field(
        None, description="Only active (true) or inactive (false) stations."
    )
    sort: StationSort = Field(
        "sort_order", description="Order: a field, «-» first for descending."
    )


class StationOut(Schema):
    id: UUID = Field(description="The station's id.")
    name: str = Field(description="Its name.")
    color: str = Field(description="Its colour, #RRGGBB.")
    destination: Destination = Field(
        description="both, display (screen only) or printer (paper only)."
    )
    printer_usage: PrinterUsage = Field(
        description="kitchen or bar: the printer function."
    )
    printer_name: str = Field(
        description="A given printer by its name; empty: the function's."
    )
    sort_order: int = Field(description="Its place.")
    is_active: bool = Field(description="Switched on: it gets only the products and categories routed to it.")
    in_progress: int = Field(description="Its dishes still to cook.")
    routes: int = Field(description="How many products and categories go to it.")


StationPage = Page[StationOut]


class StationIn(In):
    name: _text(80, 1) = Field(description="Its name (Grill).")
    color: Hex = Field(
        "#F97316", title=STATION_COLOUR, description="Its colour, #RRGGBB."
    )
    destination: Destination = Field(
        "both", description="both (screen and paper), display or printer."
    )
    printer_usage: PrinterUsage = Field(
        "kitchen", description="The printer function: kitchen or bar."
    )
    printer_name: _text(100) = Field(
        "",
        description="A given printer of Printing by its name; empty: the function's.",
    )
    sort_order: int = Field(0, ge=0, le=10_000, description="Its place in the lists.")
    is_active: bool = Field(True, description="Switched on: it gets only the products and categories routed to it.")


class StationPatchIn(StationRefIn):
    name: _text(80, 1) | None = Field(None, description="Its new name.")
    color: Hex | None = Field(
        None, title=STATION_COLOUR, description="Its colour, #RRGGBB."
    )
    destination: Destination | None = Field(
        None, description="both, display or printer."
    )
    printer_usage: PrinterUsage | None = Field(None, description="kitchen or bar.")
    printer_name: _text(100) | None = Field(
        None, description="A given printer by its name; empty: the function's."
    )
    sort_order: int | None = Field(None, ge=0, le=10_000, description="Its place.")
    is_active: bool | None = Field(None, description="Switched on: it gets only the products and categories routed to it.")
