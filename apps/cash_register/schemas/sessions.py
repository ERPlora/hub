"""The sessions of the drawer: naming one, their list and detail, the open one, opening and closing one, the daily
auto-close and the X or Z report."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.cash_register.schemas.app_lines import AppLine
from apps.cash_register.schemas.fields import (
    A_DRAWER,
    A_SESSION,
    DRAWER,
    SAY_WHICH_SESSION,
    Cents,
    Closed,
    Name,
    Notes,
    Page,
    PageIn,
    SessionNumber,
    SessionStatus,
    SignedCents,
    SortDir,
)
from base.sensitive import COSTS

class SessionRefIn(Closed):
    """Names a session; none = the open one."""

    session_id: UUID | None = Field(
        None, description="The session's id; empty = the open one.", json_schema_extra=A_SESSION
    )
    session: SessionNumber | None = Field(
        None, description="Its number, e.g. S-261014-0001; empty = the open one."
    )


class SessionGetIn(Closed):
    session_id: UUID | None = Field(None, description="The session's id.", json_schema_extra=A_SESSION)
    session: SessionNumber | None = Field(
        None, description="Its number, e.g. S-261014-0001, when the id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.session_id is None and self.session is None:
            raise ValueError(str(SAY_WHICH_SESSION))
        return self


class SessionListIn(PageIn):
    search: str | None = Field(
        None, max_length=24, description="Part of the session number."
    )
    number: SessionNumber | None = Field(
        None, description="Exactly this session number."
    )
    status: SessionStatus | None = Field(
        None, description="Only open or closed sessions."
    )
    register_id: UUID | None = Field(
        None, description="Only the sessions of this drawer."
    )
    opened_from: date | None = Field(
        None, description="Opened on this business day or later."
    )
    opened_to: date | None = Field(
        None, description="Opened on this business day or earlier."
    )
    opening_min: Cents | None = Field(
        None, description="Opening float at least, in cents."
    )
    opening_max: Cents | None = Field(
        None, description="Opening float at most, in cents."
    )
    expected_min: SignedCents | None = Field(
        None, description="Expected cash at least, in cents (closed sessions)."
    )
    expected_max: SignedCents | None = Field(
        None, description="Expected cash at most, in cents (closed sessions)."
    )
    counted_min: Cents | None = Field(
        None, description="Counted cash at least, in cents."
    )
    counted_max: Cents | None = Field(
        None, description="Counted cash at most, in cents."
    )
    difference_min: SignedCents | None = Field(
        None, description="Difference at least, in cents (negative = short)."
    )
    difference_max: SignedCents | None = Field(
        None, description="Difference at most, in cents (negative = short)."
    )
    sort: Literal[
        "opened_at",
        "number",
        "status",
        "opening_balance",
        "expected_balance",
        "closing_balance",
        "difference",
        "closed_at",
    ] = Field("opened_at", description="Column to sort by.")
    dir: SortDir = Field("desc", description="Sort direction.")


class SessionRow(Schema):
    id: UUID = Field(description="The session's id.")
    number: str = Field(description="Its number, S-AAMMDD-NNNN.")
    business_day: date = Field(description="The business day it opened on.")
    status: SessionStatus = Field(description="open or closed.")
    register_id: UUID | None = Field(description="Its drawer.")
    register_name: str = Field(description="Its drawer's name.")
    opened_at: datetime = Field(description="When it opened.")
    opened_by: str = Field(description="Who opened it.")
    opening_balance: int = Field(description="Opening float, in cents.", json_schema_extra={"money": True})
    closed_at: datetime | None = Field(description="When it closed.")
    closed_by: str = Field(description="Who closed it; empty = closed by itself.")
    closing_balance: int | None = Field(description="Counted cash, in cents.", json_schema_extra={"money": True})
    expected_balance: int | None = Field(
        description="Expected cash in cents: live while open (empty when a blind count hides it), frozen once closed.",
        json_schema_extra={"money": True},
    )
    difference: int | None = Field(description="Counted − expected, in cents.", json_schema_extra={"money": True})
    auto_closed: bool = Field(description="It closed by itself at the cut-off.")
    expected_hidden: bool = Field(
        description="A blind count hides its expected cash from the reader."
    )
    auto_close_due: bool = Field(
        description="Still open past the daily cut-off: opening a new session closes it first."
    )


SessionPage = Page[SessionRow]


class SessionSummary(Schema):
    movement_count: int = Field(description="Lines of the session.")
    opening_balance: int = Field(description="Opening float, in cents.", json_schema_extra={"money": True})
    total_sales: int | None = Field(
        description="Sales of every payment method, in cents (empty when hidden).",
        json_schema_extra={"money": True},
    )
    cash_sales: int | None = Field(description="Sales in cash, in cents (empty when hidden).", json_schema_extra={"money": True})
    card_sales: int | None = Field(description="Sales by card, in cents (empty when hidden).", json_schema_extra={"money": True})
    other_sales: int | None = Field(
        description="Sales by transfer or other methods, in cents (empty when hidden).", json_schema_extra={"money": True}
    )
    total_refunds: int | None = Field(
        description="Refunds and voids, every method, in cents (empty when hidden).",
        json_schema_extra={"money": True},
    )
    total_cash_in: int | None = Field(
        description="Money brought in by hand, in cents (empty when hidden).",
        json_schema_extra={"money": True},
    )
    total_cash_out: int | None = Field(
        description="Money taken out by hand, in cents (empty when hidden).",
        json_schema_extra={"money": True},
    )
    total_gifts: int | None = Field(
        description="Comps of the shift at cost, in cents, not cash (empty when hidden or without the costs).",
        json_schema_extra={"money": True, **COSTS})
    app_lines: list[AppLine] | None = Field(description="What other apps recorded (tips), apart from cash in and out: by app, "
        "what came in by payment method and what was paid out; only cash counts for the expected (empty when hidden).")
    expected_cash: int | None = Field(
        description="Expected cash, in cents (empty when hidden).", json_schema_extra={"money": True}
    )
    counted: int | None = Field(
        description="Counted cash, in cents (closed sessions).",
        json_schema_extra={"money": True},
    )
    difference: int | None = Field(
        description="Counted − expected, in cents (closed sessions).", json_schema_extra={"money": True}
    )


class SessionOut(SessionRow):
    opening_notes: str = Field(description="Notes written when opening.")
    closing_notes: str = Field(description="Notes written when closing.")
    summary: SessionSummary = Field(description="The figures of the session.")


class CurrentOut(Schema):
    required: bool = Field(
        description="The cash register is on: cash should only be charged with a session open."
    )
    session: SessionRow | None = Field(
        description="The open session; empty = the drawer is closed."
    )
    auto_close_at: datetime | None = Field(
        description="The cut-off the open session should have closed at, when it is due."
    )
    unassigned_count: int = Field(
        description="Sale lines that fell in no shift: with the drawer closed, after a forgotten shift's cut-off, or confirmed while the last one was closing."
    )
    unassigned_cash: int = Field(
        description="Their cash, in cents (what they put in or took out).", json_schema_extra={"money": True}
    )


class SessionOpenIn(Closed):
    register_id: UUID | None = Field(None, description="The drawer's id.", json_schema_extra=A_DRAWER)
    register_name: Name | None = Field(
        None,
        title=DRAWER,
        description="The drawer's name; with a single active drawer it is chosen alone.",
    )
    opening_balance: Cents | None = Field(
        None, description="The cash in the drawer at the start, in cents; empty = 0."
    )
    opening_notes: Notes = Field("", description="Notes of the opening.")


class SessionCloseIn(SessionRefIn):
    # The titles name each datum on the assistant's card, as the screen's «Close session» does.
    closing_balance: Cents | None = Field(
        None,
        title=gettext_noop("Counted cash"),
        description="The counted cash, in cents (required when the settings ask for the count).",
    )
    closing_notes: Notes = Field("", title=gettext_noop("Closing notes"), description="Notes of the closing.")


class AutoCloseOut(Schema):
    closed: list[SessionRow] = Field(
        description="The sessions closed now (none = nothing was due)."
    )


class SessionPrintOut(Schema):
    report: Literal["x", "z"] = Field(
        description="Which report: x (partial, the session is open) or z (the closing, the session is closed)."
    )
    job_id: UUID = Field(description="Its job in the receipt printer's queue.")
    printer: str | None = Field(
        description="The printer that will print it; none = the first device with a receipt printer."
    )
