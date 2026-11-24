"""Rectifying (INVOICE-F07–F10): a rectification by differences of what is left of a document, asked by hand or by a
sale's refund or void.
"""

import datetime as dt
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.invoice import fiscal
from apps.invoice.models import Invoice
from apps.invoice.queries.rectifying import rectifiable, rectification_figures, rectifying_type
from apps.invoice.queries.refunds import REFUND_NOT_FOUND
from apps.invoice.queries.rows import document_of_sale, find_invoice, remaining_of
from apps.invoice.queries.series import RECTIFYING
from apps.invoice.schemas.invoices import IssueOut
from apps.invoice.schemas.rectifying import FromRefundIn, FromVoidIn, RectifyIn
from apps.invoice.services.from_sale import _sale_key, _tell_sales
from apps.invoice.services.issuer import _issuer_of
from apps.invoice.services.issuing import VERBATIM, _issue, _settle_rectified
from apps.invoice.services.numbering import series_of_year
from apps.invoice.services.recipient import _recipient_of
from apps.invoice.services.writes import _now, _result, _today
from apps.sale.models import Refund, Sale
from apps.sale.queries.sales import find_sale
from apps.tax.models import TaxRule
from apps.tax.queries.calculation import round_half_up
from base.business import business_zone

SALE_NOT_INVOICED = _(
    "The sale %(number)s has no invoice yet: its rectification waits for it."
)


SALE_NOT_VOIDED = _("The sale %(number)s is not voided.")


def _rectify(  # noqa: PLR0913
    ctx: OperationContext,
    original: Invoice,
    *,
    amount: int,
    reason: str,
    invoice_type: str,
    source_type: str,
    operation_date: dt.date,
    line_description: str,
    source_refund: Refund | None = None,
    returned: dict[fiscal.FiscalKey, tuple[int, str]] | None = None,
) -> Invoice:
    """Issues the rectification by differences of ``amount`` cents of what is left of ``original``: the
    whole original negated (header, breakdown and lines) when nothing rectified it yet and the amount is
    its total; else what is left prorated key by key — over the keys of the articles ``returned`` (their
    worth and their text, per key) when a refund brings them back — with one line per key at its own
    rate (``queries.rectifying.rectification_figures``, the same the preview reads). The original is cancelled
    when nothing is left of it, and ``invoice.invoice.rectified`` says so."""
    entries, lines, _whole = rectification_figures(
        original, amount=amount, line_description=line_description, returned=returned
    )
    series = series_of_year(RECTIFYING, _today().year, ctx)
    rectification = _issue(
        ctx,
        series=series,
        invoice_type=invoice_type,
        entries=entries,
        lines=lines,
        tolerance={fiscal.key_of(item): VERBATIM for item in entries},
        recipient=_recipient_of(original),
        issuer=_issuer_of(original),
        operation_date=operation_date,
        source_type=source_type,
        source_sale=original.source_sale,
        source_refund=source_refund,
        rectifies=original,
        rectification_kind=Invoice.RectificationKind.DIFFERENCES,
        description=reason[:500],
        currency=original.currency,
    )
    _settle_rectified(ctx, original, rectification)
    return rectification


@operation(
    "invoice.invoice.rectify",
    kind="command",
    permission="invoice.rectify_invoice",
    input=RectifyIn,
    output=IssueOut,
    ai={
        "asks": {
            "en": (
                "rectify FACT-2025-000317, the amount was wrong",
                "issue an R1 rectification of FACT-2025-000317",
            ),
            "es": (
                "rectifica la FACT-2025-000317 por un error en el importe",
                "haz una rectificativa R1 de la FACT-2025-000317",
            ),
        },
        "description": "Rectify an invoice (by its number) with a mandatory reason: a rectifying invoice dated today in "
        "this year's RECT series negates what is left of it, and the original is cancelled. Type R1 by default (R2–R4 "
        "to choose; a ticket is always R5). Do not send a date: any other day than today is refused. Money is given "
        "back in Sales, not here. Read invoice.invoice.rectification_preview first with the same reason and type; "
        "then, in the same answer where you tell the person its preview, call this tool naming the invoice by the "
        "number it gave: do not stop at the preview nor wait for a yes in the chat.",
        "risk": "high",
        # Its card shows the rectifying invoice it issues, not only the number and the reason it sends; the next
        # number is read, never taken (BASE-F98).
        "preview": {
            "operation": "invoice.invoice.rectification_preview",
            "fields": ["invoice_type", "next_number", "base_amount", "tax_amount", "total_amount"],
        },
    },
)
def rectify(ctx: OperationContext, data: RectifyIn) -> dict:
    original = find_invoice(ctx, data.invoice_id, data.number, lock=True)
    left_over = rectifiable(original, _today(), data.issue_date)
    rectification = _rectify(
        ctx,
        original,
        amount=left_over,
        reason=data.reason,
        invoice_type=rectifying_type(original, data.rectification_type),
        source_type=Invoice.Source.RECTIFICATION,
        operation_date=original.operation_date,
        line_description=data.reason,
    )
    return _result(ctx, rectification, issued=True)


def _sale_document(sale: Sale) -> Invoice:
    """The document in force of ``sale``, locked; a 409 to retry while it has none (INVOICE-F06)."""
    document = document_of_sale(sale.id)
    if document is None:
        raise Conflict(
            str(SALE_NOT_INVOICED) % {"number": sale.number},
            code="invoice.sale_not_invoiced",
        )
    return Invoice.objects.select_for_update().get(pk=document.pk)


def _quantity_text(quantity: Decimal) -> str:
    """«2», «0.25»: a quantity without the zeros its three decimals add."""
    return f"{quantity.normalize():f}"


def _refund_concept(refund: Refund) -> str:
    """What came back: «2 × Shampoo, 1 × Wax», or the reason of a refund of money only."""
    returned = [
        f"{_quantity_text(item.quantity)} × {item.sale_line.name}"
        for item in refund.lines.select_related("sale_line").order_by(
            "sale_line__position", "id"
        )
    ]
    return ", ".join(returned) or refund.reason


def _returned_by_key(refund: Refund) -> dict[fiscal.FiscalKey, tuple[int, str]] | None:
    """The articles a refund brings back, per fiscal key: what they were charged (their share of their
    line) and their text («2 × Shampoo»); ``None`` for a refund of money only."""
    items = list(
        refund.lines.select_related("sale_line").order_by("sale_line__position", "id")
    )
    if not items:
        return None
    rules = TaxRule.objects.in_bulk(
        {item.sale_line.tax_rule_id for item in items if item.sale_line.tax_rule_id}
    )
    weights: dict[fiscal.FiscalKey, int] = {}
    texts: dict[fiscal.FiscalKey, list[str]] = {}
    for item in items:
        line = item.sale_line
        key = _sale_key(line, rules)
        weights[key] = weights.get(key, 0) + round_half_up(
            Decimal(line.line_total) * item.quantity / line.quantity
        )
        texts.setdefault(key, []).append(
            f"{_quantity_text(item.quantity)} × {line.name}"
        )
    return {key: (weights[key], ", ".join(texts[key])) for key in weights}


@operation(
    "invoice.invoice.rectify_from_refund",
    kind="command",
    permission="invoice.rectify_invoice",
    input=FromRefundIn,
    output=IssueOut,
    ai={
        "asks": {
            "en": (
                "issue the rectifying invoice of what was given back in sale 20261103-0012",
                "the refund of Carpintería Lema still has no rectifying invoice",
            ),
            "es": (
                "haz la factura en negativo de lo devuelto en la venta 20261103-0012",
                "la devolución de Carpintería Lema aún no tiene su rectificativa",
            ),
        },
        "description": "Issue the rectifying invoice of a refund of the Sales app (by the refund's id): what the refund "
        "gave back, prorated over what is left of the sale's invoice (by differences); the refund that closes the sale "
        "takes exactly what is left and cancels the invoice. It also happens by itself after every refund; asking "
        "again issues nothing.",
        "risk": "high",
    },
)
def rectify_from_refund(ctx: OperationContext, data: FromRefundIn) -> dict:
    refund = Refund.objects.filter(pk=data.refund_id).first()
    if refund is None:
        raise NotFound(str(REFUND_NOT_FOUND), code="invoice.refund_not_found")
    sale = find_sale(refund.sale_id, None, lock=True)
    existing = Invoice.objects.filter(source_refund=refund).first()
    if existing is not None:
        _tell_sales(ctx, existing, refund.invoice_status)
        return _result(ctx, existing, issued=False, already=True)
    original = _sale_document(sale)
    left_over = remaining_of(original)
    returned_until_now = sum(
        item.total
        for item in sale.refunds.all()
        if (item.created_at, item.id.int) <= (refund.created_at, refund.id.int)
    )
    closes = returned_until_now >= sale.total
    amount = left_over if closes else min(refund.total, left_over)
    if amount <= 0:
        return _result(ctx, None, issued=False)
    rectification = _rectify(
        ctx,
        original,
        amount=amount,
        reason=refund.reason,
        invoice_type=rectifying_type(original),
        source_type=Invoice.Source.REFUND,
        operation_date=timezone.localdate(refund.created_at, business_zone()),
        line_description=_refund_concept(refund),
        source_refund=refund,
        returned=None if closes else _returned_by_key(refund),
    )
    _tell_sales(ctx, rectification, refund.invoice_status)
    return _result(ctx, rectification, issued=True)


@operation(
    "invoice.invoice.rectify_from_void",
    kind="command",
    permission="invoice.rectify_invoice",
    input=FromVoidIn,
    output=IssueOut,
    ai={
        "asks": {
            "en": (
                "issue the rectifying invoice of voided sale 20261103-0012",
                "the cancelled sale 20261103-0012 still has no rectifying invoice",
            ),
            "es": (
                "haz la rectificativa de la venta anulada 20261103-0012",
                "a la anulación de la venta 20261103-0012 le falta su factura en negativo",
            ),
        },
        "description": "Issue the rectifying invoice of a voided sale (by the sale's id): the whole of what is left of "
        "its ticket negated (R5; R1 if the ticket was replaced by a full invoice), with the void's reason. It also "
        "happens by itself after every void; asking again issues nothing.",
        "risk": "high",
    },
)
def rectify_from_void(ctx: OperationContext, data: FromVoidIn) -> dict:
    sale = find_sale(data.sale_id, None, lock=True)
    if sale.status != Sale.Status.VOIDED:
        raise Conflict(
            str(SALE_NOT_VOIDED) % {"number": sale.number},
            code="invoice.sale_not_voided",
        )
    existing = Invoice.objects.filter(
        source_sale=sale, source_type=Invoice.Source.VOID
    ).first()
    if existing is not None:
        _tell_sales(ctx, existing, sale.void_invoice_status)
        return _result(ctx, existing, issued=False, already=True)
    original = _sale_document(sale)
    left_over = remaining_of(original)
    if left_over <= 0:
        return _result(ctx, None, issued=False)
    rectification = _rectify(
        ctx,
        original,
        amount=left_over,
        reason=sale.void_reason,
        invoice_type=rectifying_type(original),
        source_type=Invoice.Source.VOID,
        operation_date=timezone.localdate(sale.voided_at or _now(), business_zone()),
        line_description=sale.void_reason,
    )
    _tell_sales(ctx, rectification, sale.void_invoice_status)
    return _result(ctx, rectification, issued=True)
