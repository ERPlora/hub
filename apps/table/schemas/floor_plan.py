"""Whether the floor plan is set up (``table.floor.status``): how many tables are in use and how many zones there
are."""

from ninja import Field, Schema

class FloorStatusOut(Schema):
    usable_tables: int = Field(
        description="Tables in use (not deleted, active): the plan is set up with one."
    )
    zones: int = Field(description="Zones of the room.")
