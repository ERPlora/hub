"""The lines of a session: their list (or the unassigned ones), one line, and a cash in or out recorded by hand."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Field
from pydantic import model_validator

from apps.cash_register.schemas.app_lines import AppMark
from apps.cash_register.schemas.fields import (
    ONE_LIST,
    Cents,
    ManualType,
    MethodType,
    MovementType,
    Page,
    PageIn,
    PositiveCents,
    SessionNumber,
    SortDir,
    _text,
)
from apps.cash_register.schemas.sessions import SessionRefIn
from base.sensitive import COSTS

class MovementListIn(PageIn):
    session_id: UUID | None = Field(None, description="The session's id.")
    session: SessionNumber | None = Field(None, description="The session's number.")
    unassigned: bool = Field(
        False,
        description="Instead of a session: the sale lines that fell in no shift (as session.current counts them).",
    )
    search: str | None = Field(
        None, max_length=100, description="Part of the concept or of the sale number."
    )
    type: MovementType | None = Field(None, description="Only lines of this type.")
    method_type: MethodType | None = Field(
        None, description="Only lines of this payment method type."
    )
    amount_min: Cents | None = Field(None, description="Amount at least, in cents.")
    amount_max: Cents | None = Field(None, description="Amount at most, in cents.")
    sort: Literal["created_at", "amount", "type", "method_type"] = Field(
        "created_at", description="Column to sort by."
    )
    dir: SortDir = Field("desc", description="Sort direction.")

    @model_validator(mode="after")
    def _one_list(self):
        named = self.session_id is not None or self.session is not None
        if named == self.unassigned:
            raise ValueError(str(ONE_LIST))
        return self


class MovementRow(AppMark):
    key: str = Field(
        description="Stable key of the line: the movement's id, or its sale line («sale-…», «void-…», «refund-…»)."
    )
    session_id: UUID | None = Field(description="Its session; empty = it fell in none.")
    type: MovementType = Field(description="in, out, sale, refund or void.")
    amount: int = Field(description="Amount in cents, never negative.", json_schema_extra={"money": True})
    signed_amount: int = Field(
        description="With its sign: out, refunds and voids are negative.",
        json_schema_extra={"money": True, "signed": True},
    )
    method_type: MethodType = Field(
        description="cash, card, transfer or other: only cash is in the drawer."
    )
    method_name: str = Field(description="The payment method's name as Sales calls it.")
    description: str = Field(description="The concept written by hand.")
    sale_id: UUID | None = Field(description="The sale of a sale, void or refund line.")
    sale_number: str = Field(description="That sale's number.")
    document_type: str = Field(description="That sale's document: ticket or invoice.")
    gift_total: int | None = Field(description="Comps of that sale at cost, in cents (empty without the costs).", json_schema_extra={"money": True, **COSTS})
    created_at: datetime = Field(description="When.")
    created_by: str = Field(description="Who.")


MovementPage = Page[MovementRow]


class MovementAddIn(SessionRefIn):
    type: ManualType = Field(description="in (cash brought in) or out (cash taken out).")
    amount: PositiveCents = Field(description="How much, in cents, always positive: the type gives the sign.")
    method_type: MethodType = Field("cash", description="cash by default; card, transfer or other do not count for the drawer.")
    description: _text(255) = Field("", description="Why: a supplier paid, change brought in…")
    app: _text(32) | None = Field(None, description="Only another app that records its own lines (tip), by its registry "
        "name: they show apart from cash in and out. Empty when a person records it.")
