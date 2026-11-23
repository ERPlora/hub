"""Schemas of a sale's refunds: what comes back, on which tender, and how they are found."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.sale.schemas.checkout import FiscalStatus
from apps.sale.schemas.fields import (
    A_METHOD,
    A_SALE_LINE,
    A_TENDER,
    MAX_LINES,
    MAX_PAYMENTS,
    AttemptKey,
    Closed,
    MethodType,
    PositiveCents,
    Quantity,
    Reason,
    SaleStatus,
    _text,
)
from apps.sale.schemas.sales import SaleRefIn


class AllocationIn(Closed):
    payment_id: UUID = Field(description="The tender of the sale the money comes off.", json_schema_extra=A_TENDER)
    amount: PositiveCents = Field(description="What goes back on it, in cents.")
    to_method_id: UUID | None = Field(
        None,
        description="Another payment method to give it back by; empty = the tender's own.",
        json_schema_extra=A_METHOD,
    )


class RefundLineIn(Closed):
    line_id: UUID = Field(description="A line of the sale that comes back.", json_schema_extra=A_SALE_LINE)
    quantity: Quantity | None = Field(
        None, description="How many units come back; empty = all that is left."
    )


class RefundIn(SaleRefIn):
    reason: Reason = Field(description="Why the money goes back (mandatory).")
    note: _text(500) = Field("", description="A note of the refund.")
    idempotency_key: AttemptKey | None = Field(
        None, description="The attempt's key: a retry with it never refunds twice."
    )
    allocations: list[AllocationIn] = Field(
        default_factory=list,
        max_length=MAX_PAYMENTS,
        title=gettext_noop("Refund amount"),
        description="How much goes back on each tender; none = no money (only the session of a voucher).",
    )
    lines: list[RefundLineIn] = Field(
        default_factory=list,
        max_length=MAX_LINES,
        description="The lines that come back; none = only money. A line paid with a voucher gives its session back.",
    )


class RefundOut(Schema):
    already: bool = Field(description="True: this attempt had already been recorded.")
    refund_id: UUID = Field(description="The refund's id.")
    sale_id: UUID = Field(description="The sale.")
    total: int = Field(description="Refunded in cents.", json_schema_extra={"money": True})
    fully_refunded: bool = Field(
        description="Whether the sale is now refunded in full."
    )
    invoice_status: FiscalStatus = Field(
        description="Its rectifying invoice, issued by Invoicing in the same refund: issued; none (no money "
        "back, nothing to rectify); pending (Invoicing refused now and issues it later); unavailable."
    )
    invoice_number: str = Field(description="The number of its rectifying invoice (RECT-2026-000001).")
    invoice_type: str = Field(description="R5 (of a ticket) or R1 (of an invoice); empty while none.")


class TenderOption(Schema):
    payment_id: UUID = Field(description="The tender.")
    position: int = Field(description="Order taken.")
    method_id: UUID = Field(description="Its method.")
    method_name: str = Field(description="Its method's name.")
    method_type: MethodType = Field(description="Its method's type.")
    charged: int = Field(description="Charged in cents.", json_schema_extra={"money": True})
    refunded: int = Field(description="Already refunded on it, in cents.", json_schema_extra={"money": True})
    remaining: int = Field(description="Still refundable on it, in cents.", json_schema_extra={"money": True})
    refundable: bool = Field(
        description="Whether it can go back through its own method."
    )
    reason: Literal["", "already_refunded", "method_unavailable"] = Field(
        description="Why not, if it cannot."
    )


class LineOption(Schema):
    line_id: UUID = Field(description="The line.")
    name: str = Field(description="Its name.")
    unit: str = Field(description="Its unit.")
    quantity: Decimal = Field(description="Units sold.")
    returned: Decimal = Field(description="Units already back.")
    left: Decimal = Field(description="Units that can still come back.")
    line_total: int = Field(description="What the line charged, in cents.", json_schema_extra={"money": True})
    is_gift: bool = Field(description="A comp.")
    paid_by_voucher: bool = Field(
        description="A voucher session paid it: returning it gives the session back."
    )
    voucher_name: str = Field(description="The voucher that paid it.")


class RefundOptionsOut(Schema):
    sale_id: UUID = Field(description="The sale.")
    number: str = Field(description="Its number.")
    status: SaleStatus = Field(description="Its status.")
    currency: str = Field(description="ISO 4217 currency it was charged in: what goes back goes in it.")
    currency_decimals: int = Field(description="The decimals of its currency as the server counts them (0 in JPY).")
    total: int = Field(description="Its total, in minor units.", json_schema_extra={"money": True})
    refunded_total: int = Field(description="Refunded so far, in minor units.", json_schema_extra={"money": True})
    refundable_total: int = Field(description="Still refundable, in minor units.", json_schema_extra={"money": True})
    tenders: list[TenderOption] = Field(description="One row per tender, always.")
    lines: list[LineOption] = Field(description="Its lines and what is left of each.")


class RefundRow(Schema):
    id: UUID = Field(description="The refund's id.")
    sale_id: UUID = Field(description="The sale.")
    total: int = Field(description="Refunded in cents.", json_schema_extra={"money": True})
    reason: str = Field(description="Why.")
    note: str = Field(description="Note.")
    created_at: datetime = Field(description="When.")
    created_by: str = Field(description="Who.")
    invoice_status: FiscalStatus = Field(
        description="Its rectifying invoice: issued, pending (waits: «Issue now»), unavailable or none."
    )
    invoice_number: str = Field(description="The number of its rectifying invoice; empty while it has none.")
    invoice_type: str = Field(description="R5 (of a ticket) or R1 (of an invoice); empty while none.")


class RefundListOut(Schema):
    rows: list[RefundRow] = Field(description="The sale's refunds, newest first.")


class RefundByKeyIn(Closed):
    idempotency_key: AttemptKey = Field(description="The refund attempt's key.")


class RefundByKeyOut(Schema):
    found: bool = Field(description="Whether a refund was recorded with that key.")
    refund: RefundRow | None = Field(description="That refund.")
