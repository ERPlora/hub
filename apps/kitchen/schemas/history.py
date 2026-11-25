"""The History: what happened to each ticket, who did it and when."""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema

from apps.kitchen.schemas.fields import LogAction, Page, PageIn


class LogListIn(PageIn):
    search: str | None = Field(
        None, max_length=120, description="Part of the ticket's number or of the notes."
    )
    action: LogAction | None = Field(None, description="Only this action.")
    ticket_id: UUID | None = Field(None, description="Only the history of this ticket.")
    date_from: dt.date | None = Field(
        None, description="From this day (the business's), included."
    )
    date_to: dt.date | None = Field(
        None, description="Up to this day (the business's), included."
    )


class LogOut(Schema):
    id: UUID = Field(description="The entry's id.")
    action: LogAction = Field(description="What happened.")
    ticket_id: UUID = Field(description="The ticket.")
    ticket_number: str = Field(description="The ticket's number.")
    item_name: str = Field(description="The dish, for an action on one dish.")
    station_name: str = Field(description="The station of that dish.")
    actor: str = Field(description="Who did it: a person's name, an API key's or the platform's own mark (empty: the kitchen by itself).")
    by_platform: bool = Field(description="No person did it: the platform (the kitchen by itself, an automation, a recovery).")
    notes: str = Field(description="Its notes (a reason).")
    created_at: dt.datetime = Field(description="When.")


LogPage = Page[LogOut]
