"""Schemas of the people who serve the room (``table.waiter.list``)."""

from ninja import Field, Schema

from apps.table.schemas.fields import Page, PageIn

class WaiterListIn(PageIn):
    search: str | None = Field(
        None, max_length=128, description="Part of the person's name."
    )


class WaiterOut(Schema):
    id: str = Field(description="The person's id.")
    name: str = Field(description="Their name.")


WaiterPage = Page[WaiterOut]
