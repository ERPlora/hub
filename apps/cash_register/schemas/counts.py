"""The counts of the drawer: the notes and coins counted, a session's counts and a new one, and what a count must
bring: some note or coin counted, or a total typed by hand (zero too)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import model_validator

from apps.cash_register.schemas.fields import (
    SAY_WHICH_SESSION,
    Cents,
    Closed,
    CountType,
    FaceValue,
    Page,
    PageIn,
    Pieces,
    SessionNumber,
    SortDir,
    _text,
)
from apps.cash_register.schemas.sessions import SessionRefIn

COUNT_SOMETHING = _("Count the drawer: give its notes and coins or its total.")


def counts_something(denominations, total: int | None) -> bool:
    """Whether a count's ``denominations`` (bills and coins, face value → pieces) or its ``total`` count anything."""
    if total is not None:
        return True
    if denominations is None:
        return False
    return any(pieces > 0 for kind in (denominations.bills, denominations.coins) for pieces in kind.values())


class Denominations(Closed):
    bills: dict[FaceValue, Pieces] = Field(
        default_factory=dict,
        description="Notes: face value in major units («50») → how many.",
    )
    coins: dict[FaceValue, Pieces] = Field(
        default_factory=dict,
        description="Coins: face value in major units («0.50») → how many.",
    )


class CountListIn(PageIn):
    session_id: UUID | None = Field(None, description="The session's id.")
    session: SessionNumber | None = Field(None, description="The session's number.")
    sort: Literal["counted_at", "total", "type"] = Field(
        "counted_at", description="Column to sort by."
    )
    dir: SortDir = Field("desc", description="Sort direction.")

    @model_validator(mode="after")
    def _named(self):
        if self.session_id is None and self.session is None:
            raise ValueError(str(SAY_WHICH_SESSION))
        return self


class CountOut(Schema):
    id: UUID = Field(description="The count's id.")
    session_id: UUID = Field(description="Its session.")
    type: CountType = Field(description="opening or closing.")
    total: int = Field(description="Total counted, in cents.", json_schema_extra={"money": True})
    denominations: dict = Field(description="The notes and coins counted.")
    notes: str = Field(description="Notes.")
    counted_at: datetime = Field(description="When.")
    counted_by: str = Field(description="Who.")


CountPage = Page[CountOut]


class CountAddIn(SessionRefIn):
    type: CountType = Field(
        "closing",
        description="closing (end of the shift) or opening (check the float).",
    )
    denominations: Denominations | None = Field(
        None, description="The notes and coins counted; the server adds them up."
    )
    total: Cents | None = Field(
        None,
        description="The total counted, in cents, when not counted by notes and coins; it prevails.",
    )
    notes: _text(500) = Field("", description="Notes of the count.")

    @model_validator(mode="after")
    def _counted(self):
        if not counts_something(self.denominations, self.total):
            raise ValueError(str(COUNT_SOMETHING))
        return self
