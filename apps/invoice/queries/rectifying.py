"""Rectifying (INVOICE-F07–F10): what a rectification issues, before it does."""

import datetime as dt
from decimal import Decimal

from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.invoice import fiscal
from apps.invoice.models import Invoice
from apps.invoice.queries.rows import find_invoice, remaining_of
from apps.invoice.queries.series import RECTIFYING, next_number_of
from apps.invoice.schemas.rectifying import RectificationPreviewIn, RectificationPreviewOut
from apps.invoice.withholding import columns
from apps.tax.queries.jurisdiction import business_today

CANNOT_RECTIFY_RECTIFICATION = _("A rectifying invoice cannot be rectified.")
ALREADY_CANCELLED = _("The invoice is already cancelled.")
SUBSTITUTED = _("This ticket was already replaced by a full invoice: rectify the full invoice.")
RECTIFY_DATE = _(
    "A rectifying invoice is dated the day it is issued: today, and never earlier than the invoice it "
    "corrects. Nothing was issued. Send it without a date and it will be dated today."
)
NOTHING_LEFT = _("Nothing is left to rectify on this invoice.")


def rectifying_type(original: Invoice, chosen: str | None = None) -> str:
    """R5 for a ticket; for a full invoice the type chosen, R1 by default (a refund is art. 80 Two)."""
    return "R5" if original.is_simplified else (chosen or "R1")


def rectifiable(
    original: Invoice, today: dt.date, issue_date: dt.date | None = None
) -> int:
    """What is left of ``original`` to rectify by hand, dated ``today`` (``issue_date``: the date asked, if any); a
    ``Conflict`` saying why when it cannot be: a rectifying invoice, a cancelled one, a ticket replaced by a full
    invoice, another day than today, nothing left."""
    if original.is_rectification:
        raise Conflict(
            str(CANNOT_RECTIFY_RECTIFICATION),
            code="invoice.cannot_rectify_rectification",
        )
    if original.status == Invoice.Status.CANCELLED:
        raise Conflict(str(ALREADY_CANCELLED), code="invoice.already_cancelled")
    if Invoice.objects.filter(substitutes=original).exists():
        raise Conflict(str(SUBSTITUTED), code="invoice.substituted")
    if (issue_date is not None and issue_date != today) or original.issue_date > today:
        raise Conflict(
            str(RECTIFY_DATE),
            code="invoice.rectify_date_not_allowed",
            fields={"issue_date": str(RECTIFY_DATE)},
        )
    left_over = remaining_of(original)
    if left_over <= 0:
        raise Conflict(str(NOTHING_LEFT), code="invoice.nothing_left")
    return left_over


def key_line(item: dict, description: str, returned: dict | None) -> dict:
    """The line of one key of a rectification by differences: its base as the price, at its own rate,
    named by the articles of that key that came back (else by ``description``)."""
    key = fiscal.key_of(item)
    text = (returned or {}).get(key, (0, ""))[1] or description
    return {
        "description": text[:255],
        "quantity": Decimal("-1"),
        "unit_price": Decimal(-item["base"]),
        "discount_amount": 0,
        "tax_rate": key.rate,
        "surcharge_rate": key.surcharge_rate,
        "base_amount": item["base"],
        "tax_amount": item["quota"] + item["surcharge_quota"],
        "total_amount": fiscal.gross_of(item),
    }


def rectification_figures(
    original: Invoice,
    *,
    amount: int,
    line_description: str,
    returned: dict[fiscal.FiscalKey, tuple[int, str]] | None = None,
) -> tuple[list[dict], list[dict], bool]:
    """The breakdown and the lines of the rectification by differences of ``amount`` cents of what is left of
    ``original``, and whether it is the whole original: the whole original negated (breakdown and lines) when nothing
    rectified it yet and the amount is its total; else what is left prorated key by key — over the keys of the
    articles ``returned`` (their worth and their text, per key) when a refund brings them back — with one line per
    key at its own rate. What the preview says and what the rectification writes are these same figures."""
    previous = list(original.rectifications.all())
    if not previous and amount == original.total_amount:
        entries = fiscal.negate(original.tax_breakdown)
        lines = [
            {
                "description": line.description,
                "quantity": -line.quantity,
                "unit_price": line.unit_price,
                "discount_amount": -line.discount_amount,
                "tax_rate": line.tax_rate,
                "surcharge_rate": line.surcharge_rate,
                "tax_category_key": line.tax_category_key,
                "base_amount": -line.base_amount,
                "tax_amount": -line.tax_amount,
                "total_amount": -line.total_amount,
                "product_id": line.product_id,
                "sale_line_id": line.sale_line_id,
            }
            for line in original.lines.order_by("position", "id")
        ]
        return entries, lines, True
    left = fiscal.remaining(
        original.tax_breakdown, [item.tax_breakdown for item in previous]
    )
    weights = (
        [returned.get(fiscal.key_of(item), (0, ""))[0] for item in left]
        if returned
        else None
    )
    entries = [
        item
        for item in fiscal.prorate(left, amount, weights)
        if fiscal.gross_of(item) or item["base"]
    ]
    lines = [key_line(item, line_description, returned) for item in entries]
    return entries, lines, False


@operation(
    "invoice.invoice.rectification_preview",
    kind="query",
    permission="invoice.rectify_invoice",
    input=RectificationPreviewIn,
    output=RectificationPreviewOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "before rectifying FACT-2025-000317, show me what would be issued",
                "preview the rectification of FACT-2025-000317 without issuing it",
            ),
            "es": (
                "antes de rectificar la FACT-2025-000317, enséñame cómo quedaría",
                "¿qué rectificativa saldría de la FACT-2025-000317 si la corrijo ahora?",
            ),
        },
        "description": "The rectifying invoice that rectifying an invoice (by its number) with that reason and type "
        "would issue now, before issuing it: the invoice it rectifies (number, date, customer, total and what is left "
        "of it), its type (R1 by default, R5 for a ticket), the reason, this year's RECT series and the next number "
        "(NOT reserved: say it as the next one), today's date, and its base, tax, total and lines in negative. Changes "
        "nothing and takes no number. To rectify, read it with the reason and type said and, in the same answer "
        "where you tell the person this preview, call invoice.invoice.rectify: do not wait for a yes in the chat. "
        "When the invoice cannot be rectified it says why, and there is nothing to rectify."
    },
)
def rectification_preview(
    ctx: OperationContext, params: RectificationPreviewIn
) -> dict:
    original = find_invoice(ctx, params.invoice_id, params.number)
    today = business_today()
    left_over = rectifiable(original, today)
    entries, lines, whole = rectification_figures(
        original, amount=left_over, line_description=params.reason
    )
    base = sum(item["base"] for item in entries)
    tax = sum(item["quota"] + item["surcharge_quota"] for item in entries)
    withholding = columns(base, original.withholding_rate)
    return {
        "original": {
            "invoice_id": original.id,
            "number": original.number,
            "invoice_type": original.invoice_type,
            "issue_date": original.issue_date,
            "customer_name": original.customer_name,
            "total_amount": original.total_amount,
            "remaining": left_over,
        },
        "invoice_type": rectifying_type(original, params.rectification_type),
        "reason": params.reason,
        "series_code": RECTIFYING,
        "next_number": next_number_of(RECTIFYING, today.year),
        "issue_date": today,
        "whole": whole,
        "base_amount": base,
        "tax_amount": tax,
        "total_amount": base + tax,
        **withholding,
        "payable_amount": base + tax - withholding["withholding_amount"],
        "currency": original.currency,
        "currency_decimals": get_currency_precision(original.currency),
        "lines": [
            {
                "description": line["description"],
                "quantity": line["quantity"],
                "tax_rate": line["tax_rate"],
                "base_amount": line["base_amount"],
                "total_amount": line["total_amount"],
            }
            for line in lines
        ],
    }
