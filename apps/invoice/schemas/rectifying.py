"""Schemas of the rectifying invoices: previewing and issuing one by hand, and the one a refund or a voided sale
of the Sales app issues.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ConfigDict

from apps.invoice.schemas.fields import A_REFUND, A_SALE, NEXT_NUMBER, SALE, InvoiceRefIn, InvoiceTypeCode, _text

RectificationType = Literal["R1", "R2", "R3", "R4"]


class RectificationPreviewIn(InvoiceRefIn):
    """The invoice to rectify, with the reason and the type the rectification will be sent with."""

    reason: _text(500, min_length=1) = Field(
        description="Why it is rectified; printed on the rectifying invoice."
    )
    rectification_type: RectificationType | None = Field(
        None,
        title=gettext_noop("Type of rectifying invoice"),
        description="R1 error founded in law and art. 80 One, Two and Six LIVA (default), R2 insolvency, R3 bad "
        "debts, R4 other causes. A simplified invoice (ticket) is always rectified as R5.",
        # No field of the models has this name: the assistant's card says each code by the kinds of ``invoice_type``.
        json_schema_extra={"choices_of": "invoice_type"},
    )


class RectifyIn(RectificationPreviewIn):
    """A rectification of what is left of an invoice, dated today."""

    issue_date: dt.date | None = Field(
        None,
        description="Leave it out: a rectifying invoice is dated the day it is issued, and any other day is refused.",
    )


class FromRefundIn(Schema):
    """A refund of the Sales app (also the payload of ``sale.sale.refunded``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    refund_id: UUID = Field(
        title=gettext_noop("Sale refund"),
        description="Id of the refund document of the Sales app.",
        json_schema_extra=A_REFUND,
    )


class FromVoidIn(Schema):
    """A voided sale (also the payload of ``sale.sale.voided``, whose other keys are ignored)."""

    model_config = ConfigDict(extra="ignore")

    sale_id: UUID = Field(title=SALE, description="Id of the voided sale.", json_schema_extra=A_SALE)


class RectifiedOut(Schema):
    invoice_id: UUID = Field(description="The invoice that would be rectified.")
    number: str = Field(description="Its number: name it to rectify exactly this one.")
    invoice_type: str = Field(description="Its type: F1, F2 ticket or F3.")
    issue_date: dt.date = Field(description="Its issue date.")
    customer_name: str = Field(description="Its recipient; empty on a ticket without one.")
    total_amount: int = Field(description="Its total, in cents.", json_schema_extra={"money": True})
    remaining: int = Field(
        description="What is left of it before this rectification, in cents (less than its total after a partial "
        "rectification by differences).",
        json_schema_extra={"money": True},
    )


class PreviewLineOut(Schema):
    description: str
    quantity: Decimal = Field(description="Negative: the quantity carries the sign, the price does not.")
    tax_rate: Decimal = Field(description="Its rate, %.")
    base_amount: int = Field(description="Its base, in cents (negative).", json_schema_extra={"money": True})
    total_amount: int = Field(description="Its total with tax, in cents (negative).", json_schema_extra={"money": True})


class RectificationPreviewOut(Schema):
    """The rectifying invoice that rectifying would issue now, before it is issued: nothing is written.
    ``invoice.invoice.rectify`` shows its type, next number and amounts on the card the assistant asks to confirm it
    with: their titles are the names the Invoicing screens give them, its type a closed list said by its name, and an
    amount says «in cents» to be shown as money."""

    original: RectifiedOut = Field(description="The invoice it rectifies.")
    invoice_type: InvoiceTypeCode = Field(
        title=gettext_noop("Type of rectifying invoice"),
        description="The rectification's type: R1–R4 for an invoice, R5 for a ticket.",
    )
    reason: str = Field(description="Its reason, printed on it.")
    series_code: str = Field(description="Its series: this year's rectifying one (RECT).")
    next_number: str = Field(
        title=NEXT_NUMBER,
        description="The number it would carry if issued now: the series' next one, NOT reserved — it is taken only "
        "when the rectification is issued, so another one issued before takes it. Say it as the next number, never as "
        "its own."
    )
    issue_date: dt.date = Field(description="Its date: today, the day it is issued.")
    whole: bool = Field(
        description="True: the whole original negated, line by line. False: what is left of it, one line per tax rate."
    )
    base_amount: int = Field(title=gettext_noop("Tax base"), description="Its base, in cents (negative).", json_schema_extra={"money": True})
    tax_amount: int = Field(title=gettext_noop("Tax"), description="Its tax, in cents (negative).", json_schema_extra={"money": True})
    total_amount: int = Field(description="Its total, in cents (negative).", json_schema_extra={"money": True})
    currency: str
    currency_decimals: int = Field(description="The decimals of its currency (2 in EUR): its amounts' minor unit.")
    lines: list[PreviewLineOut] = Field(description="Its lines.")
