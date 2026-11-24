"""Schemas of ERPlora's support access to the business (``base.support_access.*``)."""

import datetime as dt

from ninja import Field, Schema


class SupportAccessIn(Schema):
    """No input."""


class SupportVisitOut(Schema):
    person: str = Field(description="Who of ERPlora's support came in: their name, else their email.")
    entered_at: dt.datetime


class SupportAccessOut(Schema):
    enabled: bool = Field(description="Whether ERPlora's support may come into the business; it comes off.")
    can_change: bool = Field(description="Whether who asks may change it (who runs the business).")
    updated_by: str = Field(description="Who changed it last; empty if nobody has.")
    updated_at: dt.datetime | None
    visits: list[SupportVisitOut] = Field(description="The last entries of support, the most recent first.")


class SupportAccessUpdateIn(Schema):
    enabled: bool
