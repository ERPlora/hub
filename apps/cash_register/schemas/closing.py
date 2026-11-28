"""What closing a session would give before it closes, and what is still open at the close (the shift review)."""

from datetime import datetime
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.cash_register.schemas.fields import DRAWER, Cents
from apps.cash_register.schemas.sessions import SessionRefIn

class ClosingSummaryIn(SessionRefIn):
    closing_balance: Cents | None = Field(
        None,
        description="The counted cash, in cents, as it will be sent to close (required when the settings ask for "
        "the count).",
    )


class ShiftReviewOut(Schema):
    """What is still open when the drawer closes: it warns, it never prevents."""

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
    """What closing a session would give, before it closes: nothing is written. ``cash_register.session.close``
    shows its number, drawer, expected and difference on the card the assistant asks to confirm it with: their
    titles are the names the Cash register screens give them (the difference's is its model's), an amount says «in
    cents» to be shown as money and the difference is signed, to be shown with its sign as the screens write it."""

    session_id: UUID = Field(description="The session that would close.")
    number: str = Field(
        title=gettext_noop("Session"),
        description="Its number, S-AAMMDD-NNNN: name it to close exactly this one.",
    )
    register_name: str = Field(title=DRAWER, description="Its drawer's name; empty = no drawer.")
    opened_at: datetime = Field(description="When it opened.")
    opened_by: str = Field(description="Who opened it.")
    opening_balance: int = Field(description="Its opening float, in cents.", json_schema_extra={"money": True})
    closing_balance: int | None = Field(
        description="The counted cash said, in cents; none = closing without a count.",
        json_schema_extra={"money": True},
    )
    expected_balance: int | None = Field(
        title=gettext_noop("Expected in the drawer"),
        description="The cash there should be now, in cents; none when a blind count hides it from the reader.",
        json_schema_extra={"money": True},
    )
    difference: int | None = Field(
        description="Counted − expected, in cents (positive = over, negative = short); none without a count or "
        "when the expected is hidden.",
        json_schema_extra={"signed": True, "money": True},
    )
    expected_hidden: bool = Field(
        description="A blind count hides the expected (and so the difference) from the reader: never guess them."
    )
    require_closing_balance: bool = Field(description="The settings ask for the count to close.")
    pending: ShiftReviewOut = Field(description="What is still pending at the close (the shift review).")
