"""Input and output schemas of the cash register app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in whole cents and an amount is never negative: the type says whether it comes in or goes out. What a
person names aloud is accepted besides the id: a session by its number, a drawer by its name; and when
an operation on the open session names none, it is the open one («close the till»).
"""

from datetime import date, datetime
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict, StringConstraints, model_validator

T = TypeVar("T")

#: Just under ten trillion minor units of the business's currency (ninety-nine billion with two decimals): far above
#: any drawer, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Pieces of one note or coin in a count: more than any drawer holds.
MAX_PIECES = 100_000

SAY_WHICH_SESSION = _("Say which session: its id or its number.")
SAY_WHICH_DRAWER = _("Say which drawer: its id or its name.")
NOTHING_TO_CHANGE = _(
    "Say what changes: the drawer's new name, or whether it is active."
)
ONE_LIST = _(
    "Ask for the lines of one session (its id or number) or for the unassigned ones, one of the two."
)
COUNT_SOMETHING = _("Count the drawer: give its notes and coins or its total.")
#: How «Open session» and the drawers of the settings name a drawer (the assistant's card names the datum by it).
DRAWER = gettext_noop("Drawer")


def _text(max_length: int, min_length: int = 0) -> type[str]:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(100, 1)
SessionNumber = _text(24, 1)
Notes = _text(1000)
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS)]
PositiveCents = Annotated[int, Field(ge=1, le=MAX_CENTS)]
SignedCents = Annotated[int, Field(ge=-MAX_CENTS, le=MAX_CENTS)]
#: A note or coin by its face value in major units («50», «0.50», «0.005»).
FaceValue = Annotated[str, StringConstraints(pattern=r"^\d{1,6}(\.\d{1,3})?$")]
Pieces = Annotated[int, Field(ge=0, le=MAX_PIECES)]
#: A whole hour of the day, «00:00» to «23:00».
WholeHour = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):00$")]
MethodType = Literal["cash", "card", "transfer", "other"]
SessionStatus = Literal["open", "closed"]
MovementType = Literal["in", "out", "sale", "refund", "void"]
ManualType = Literal["in", "out"]
CountType = Literal["opening", "closing"]
SortDir = Literal["asc", "desc"]


class Closed(Schema):
    """An input that refuses fields it does not know (a typo is a 422, never silently ignored)."""

    model_config = ConfigDict(extra="forbid")


class EmptyIn(Closed):
    pass


class PageIn(Closed):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")


# ── Settings ──────────────────────────────────────────────────────────────────────────────────────


class SettingsFields(Schema):
    enable_cash_register: bool = Field(
        description="The cash register is on: Sales asks for an open session before charging in cash."
    )
    require_opening_balance: bool = Field(
        description="A session cannot open without an opening float above zero."
    )
    require_closing_balance: bool = Field(
        description="A session cannot close without the counted cash."
    )
    allow_negative_balance: bool = Field(
        description="A cash-out may leave the expected cash below zero."
    )
    require_blind_count: bool = Field(
        description="Blind count: whoever counts does not see the expected cash of an open session, unless allowed."
    )
    auto_close_enabled: bool = Field(
        description="A session still open at the cut-off hour closes by itself."
    )
    auto_close_time: WholeHour = Field(
        description="The cut-off hour of the daily auto-close, business time, «04:00»."
    )


class SettingsOut(SettingsFields):
    updated_at: datetime | None = Field(
        description="When they were last saved; empty = the factory values."
    )


class SettingsPatchIn(Closed):
    enable_cash_register: bool | None = Field(
        None, description="The cash register is on."
    )
    require_opening_balance: bool | None = Field(
        None, description="Require an opening float."
    )
    require_closing_balance: bool | None = Field(
        None, description="Require the counted cash to close."
    )
    allow_negative_balance: bool | None = Field(
        None, description="Allow a cash-out to leave the drawer below zero."
    )
    require_blind_count: bool | None = Field(None, description="Blind count.")
    auto_close_enabled: bool | None = Field(None, description="Daily auto-close.")
    auto_close_time: WholeHour | None = Field(
        None, description="The cut-off hour, «00:00» to «23:00»."
    )


# ── Drawers ───────────────────────────────────────────────────────────────────────────────────────


class RegisterListIn(PageIn):
    search: str | None = Field(
        None, max_length=100, description="Part of the drawer's name."
    )
    is_active: bool | None = Field(
        None, description="Only active (or inactive) drawers."
    )


class RegisterOut(Schema):
    id: UUID = Field(description="The drawer's id.")
    name: str = Field(description="Its name.")
    is_active: bool = Field(description="It can be chosen when opening a session.")


RegisterPage = Page[RegisterOut]


class RegisterIn(Closed):
    name: Name = Field(description="The drawer's name, e.g. Bar.")


class RegisterUpdateIn(Closed):
    register_id: UUID | None = Field(None, description="The drawer's id.")
    register_name: Name | None = Field(
        None, title=DRAWER, description="Its name, when the id is not known."
    )
    name: Name | None = Field(None, description="Its new name.")
    is_active: bool | None = Field(
        None, description="Activate (true) or deactivate (false) it."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.register_id is None and self.register_name is None:
            raise ValueError(str(SAY_WHICH_DRAWER))
        if self.name is None and self.is_active is None:
            raise ValueError(str(NOTHING_TO_CHANGE))
        return self


# ── Sessions ──────────────────────────────────────────────────────────────────────────────────────


class SessionRefIn(Closed):
    """Names a session; none = the open one."""

    session_id: UUID | None = Field(
        None, description="The session's id; empty = the open one."
    )
    session: SessionNumber | None = Field(
        None, description="Its number, e.g. S-261014-0001; empty = the open one."
    )


class SessionGetIn(Closed):
    session_id: UUID | None = Field(None, description="The session's id.")
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
    opening_balance: int = Field(description="Opening float, in cents.")
    closed_at: datetime | None = Field(description="When it closed.")
    closed_by: str = Field(description="Who closed it; empty = closed by itself.")
    closing_balance: int | None = Field(description="Counted cash, in cents.")
    expected_balance: int | None = Field(
        description="Expected cash in cents: live while open (empty when a blind count hides it), frozen once closed."
    )
    difference: int | None = Field(description="Counted − expected, in cents.")
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
    opening_balance: int = Field(description="Opening float, in cents.")
    total_sales: int | None = Field(description="Sales of every payment method, in cents (empty when hidden).")
    cash_sales: int | None = Field(description="Sales in cash (empty when hidden).")
    card_sales: int | None = Field(description="Sales by card (empty when hidden).")
    other_sales: int | None = Field(
        description="Sales by transfer or other methods (empty when hidden)."
    )
    total_refunds: int | None = Field(description="Refunds and voids, every method, in cents (empty when hidden).")
    total_cash_in: int | None = Field(description="Money brought in by hand, in cents (empty when hidden).")
    total_cash_out: int | None = Field(description="Money taken out by hand, in cents (empty when hidden).")
    total_gifts: int | None = Field(
        description="Comps of the shift at cost, in cents, not cash (empty when hidden)."
    )
    expected_cash: int | None = Field(
        description="Expected cash, in cents (empty when hidden)."
    )
    counted: int | None = Field(description="Counted cash, in cents (closed sessions).")
    difference: int | None = Field(
        description="Counted − expected, in cents (closed sessions)."
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
        description="Their cash, in cents (what they put in or took out)."
    )


class SessionOpenIn(Closed):
    register_id: UUID | None = Field(None, description="The drawer's id.")
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


class ClosingSummaryIn(SessionRefIn):
    closing_balance: Cents | None = Field(
        None,
        description="The counted cash, in cents, as it will be sent to close (required when the settings ask for "
        "the count).",
    )


class ShiftReviewOut(Schema):
    """What is still open when the drawer closes (CASH_REGISTER-F08): it warns, it never prevents."""

    open_checks: int = Field(description="Checks still open in Sales.")
    open_check_labels: list[str] = Field(description="Their titles, at most 20.")
    unserved: int = Field(description="Kitchen tickets not served yet: being cooked or waiting at the pass.")
    unserved_labels: list[str] = Field(description="Their table or number, at most 20.")
    prints: int = Field(description="Prints that did not come out: waiting or failed.")
    print_usages: list[str] = Field(
        description="The printing functions they wait in: receipt, kitchen, bar or label."
    )
    incomplete: bool = Field(
        description="One of these could not be read (no permission or a failure): the review may be incomplete."
    )


class ClosingSummaryOut(Schema):
    """What closing a session would give, before it closes (CASH_REGISTER-F09): nothing is written.
    ``cash_register.session.close`` shows its number, drawer, expected and difference on its card (BASE-F98): their
    titles are the names the Cash register screens give them (the difference's is its model's), and an amount says
    «in cents» to be shown as money."""

    session_id: UUID = Field(description="The session that would close.")
    number: str = Field(
        title=gettext_noop("Session"),
        description="Its number, S-AAMMDD-NNNN: name it to close exactly this one.",
    )
    register_name: str = Field(title=DRAWER, description="Its drawer's name; empty = no drawer.")
    opened_at: datetime = Field(description="When it opened.")
    opened_by: str = Field(description="Who opened it.")
    opening_balance: int = Field(description="Its opening float, in cents.")
    closing_balance: int | None = Field(
        description="The counted cash said, in cents; none = closing without a count."
    )
    expected_balance: int | None = Field(
        title=gettext_noop("Expected in the drawer"),
        description="The cash there should be now, in cents; none when a blind count hides it from the reader.",
    )
    difference: int | None = Field(
        description="Counted − expected, in cents (positive = over, negative = short); none without a count or "
        "when the expected is hidden."
    )
    expected_hidden: bool = Field(
        description="A blind count hides the expected (and so the difference) from the reader: never guess them."
    )
    require_closing_balance: bool = Field(description="The settings ask for the count to close.")
    pending: ShiftReviewOut = Field(description="What is still pending at the close (the shift review).")


class AutoCloseOut(Schema):
    closed: list[SessionRow] = Field(
        description="The sessions closed now (none = nothing was due)."
    )


class SessionPrintOut(Schema):
    report: Literal["x", "z"] = Field(
        description="Which report: x (partial, the session is open) or z (the closing, the session is closed)."
    )
    queued: bool = Field(
        description="It went to the receipt printer's queue. False = Printing is not on in this business: the "
        "screen prints it through the browser."
    )
    job_id: UUID | None = Field(description="Its print job, when queued.")
    printer: str | None = Field(
        description="The printer that will print it; none = the first device with a receipt printer."
    )


# ── Movements ─────────────────────────────────────────────────────────────────────────────────────


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


class MovementRow(Schema):
    key: str = Field(
        description="Stable key of the line: the movement's id, or its sale line («sale-…», «void-…», «refund-…»)."
    )
    session_id: UUID | None = Field(description="Its session; empty = it fell in none.")
    type: MovementType = Field(description="in, out, sale, refund or void.")
    amount: int = Field(description="Amount in cents, never negative.")
    signed_amount: int = Field(
        description="With its sign: out, refunds and voids are negative."
    )
    method_type: MethodType = Field(
        description="cash, card, transfer or other: only cash is in the drawer."
    )
    method_name: str = Field(description="The payment method's name as Sales calls it.")
    description: str = Field(description="The concept written by hand.")
    sale_id: UUID | None = Field(description="The sale of a sale, void or refund line.")
    sale_number: str = Field(description="That sale's number.")
    document_type: str = Field(description="That sale's document: ticket or invoice.")
    gift_total: int = Field(description="Comps of that sale at cost, in cents.")
    created_at: datetime = Field(description="When.")
    created_by: str = Field(description="Who.")


MovementPage = Page[MovementRow]


class MovementAddIn(SessionRefIn):
    type: ManualType = Field(
        description="in (cash brought in) or out (cash taken out)."
    )
    amount: PositiveCents = Field(
        description="How much, in cents, always positive: the type gives the sign."
    )
    method_type: MethodType = Field(
        "cash",
        description="cash by default; card, transfer or other do not count for the drawer.",
    )
    description: _text(255) = Field(
        "", description="Why: a supplier paid, change brought in…"
    )


# ── Counts ────────────────────────────────────────────────────────────────────────────────────────


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
    total: int = Field(description="Total counted, in cents.")
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
        if self.denominations is None and self.total is None:
            raise ValueError(str(COUNT_SOMETHING))
        return self


# ── Currency ──────────────────────────────────────────────────────────────────────────────────────


class CurrencyOut(Schema):
    currency: str = Field(description="The business's currency, ISO 4217.")
    decimals: int = Field(description="Its decimals: 2 in EUR, 0 in JPY, 3 in KWD.")
    bills: list[str] = Field(
        description="Its notes, largest first (face value in major units); empty = no table."
    )
    coins: list[str] = Field(description="Its coins, largest first; empty = no table.")
