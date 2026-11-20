"""The audit events of VeriFactu: one event, and the list of them."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.verifactu.schemas.fields import SEARCH, Direction, KindCode, OptionalText, PageIn, SeverityCode


class EventOut(Schema):
    id: UUID = Field(description="Id of the event.")
    created_at: dt.datetime = Field(description="When it happened.")
    kind: KindCode = Field(description="What happened.")
    severity: SeverityCode = Field(
        description="debug, info, warning, error or critical."
    )
    message: str = Field(description="What happened, in the reader's language.")
    record_id: UUID | None = Field(description="The record it is about, if any.")
    invoice_number: str = Field(description="Number of that record's invoice, if any.")


class EventListIn(PageIn):
    search: OptionalText(120) = Field(
        None, description=SEARCH + " In the type or the message, in Spanish or English."
    )
    kind: KindCode | None = Field(None, description="Only this type.")
    severity: SeverityCode | None = Field(None, description="Only this severity.")
    date_from: dt.date | None = Field(None, description="On this day or later.")
    date_to: dt.date | None = Field(None, description="On this day or earlier.")
    sort: Literal["created_at", "kind", "severity"] | None = Field(
        None, description="Column to sort by (the newest first by default)."
    )
    dir: Direction = Field("desc", description="asc or desc.")
