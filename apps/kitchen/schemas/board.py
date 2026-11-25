"""The board: the tickets being cooked and those waiting at the pass, with the stations their dishes go to;
and the all-day count of what is left to cook."""

from decimal import Decimal
from uuid import UUID

from ninja import Field, Schema

from apps.kitchen.schemas.fields import In, StationScope
from apps.kitchen.schemas.tickets import TicketOut


class BoardIn(In):
    station: StationScope


class StationChipOut(Schema):
    id: UUID | None = Field(description="The station; none = «No station».")
    name: str = Field(description="Its name.")
    color: str = Field(description="Its colour (#RRGGBB); empty with no station.")


class BoardOut(Schema):
    cooking: list[TicketOut] = Field(
        description="The tickets being cooked: rush, then VIP, then the rest, oldest first."
    )
    ready: list[TicketOut] = Field(
        description="The tickets waiting at the pass, oldest first."
    )
    cooking_count: int = Field(description="How many tickets are being cooked.")
    ready_count: int = Field(description="How many tickets wait at the pass.")
    stations: list[StationChipOut] = Field(
        description="The stations the dishes on the board go to."
    )
    truncated: bool = Field(
        description="More tickets are on the line than the board shows (200)."
    )


class AllDayIn(In):
    station: StationScope


class AllDayRowOut(Schema):
    product_id: UUID | None = Field(description="Inventory's product, if it is one.")
    name: str = Field(description="The dish.")
    unit: str = Field(description="Its unit.")
    station_id: UUID | None = Field(description="Its station; none = «No station».")
    station_name: str = Field(description="The station's name.")
    quantity: Decimal = Field(description="How many are left to cook.")


class AllDayOut(Schema):
    rows: list[AllDayRowOut] = Field(description="What is left to cook, most first.")
