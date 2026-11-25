"""Input and output schemas of Online orders' operations (OpenAPI, live params, 422 per field).

A table is said as Tables says it (``apps.table.schemas.TableRefIn``: its id, or its number and, if the number
repeats, its zone), so the assistant's card names it as the floor plan does."""

from datetime import datetime
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict


class TableCodeListIn(Schema):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(50, ge=1, le=100, description="How many tables to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many tables to skip, to read the next pages.")


class TableCodeOut(Schema):
    table_id: UUID = Field(description="The table's id, in Tables.")
    table: str = Field(description="The table as the floor plan names it: its number with its zone («5 (Terrace)»).")
    number: str = Field(description="The table's number.")
    zone_name: str | None = Field(description="The table's zone, if it has one.")
    code: str | None = Field(description="The code its QR carries; none until its QR is generated the first time.")
    url: str | None = Field(description="The address of the table's page, which its QR opens; none without a code.")
    issued_at: datetime | None = Field(description="When its code was generated; none without a code.")


class TableCodePage(Schema):
    rows: list[TableCodeOut] = Field(description="The tables of this page, in the floor plan's order.")
    total: int = Field(description="How many tables there are, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The tables skipped before this page.")
