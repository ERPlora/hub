"""The document of a sale (INVOICE-F01, F02, F06): its ticket or its full invoice, read from the sale itself, and
Sales given the document it waits for.
"""

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.operations import get as get_operation

from apps.invoice import events, fiscal
from apps.invoice.models import Invoice
from apps.invoice.queries.series import FULL, TICKET
from apps.invoice.schemas.invoices import FromSaleIn, IssueOut
from apps.invoice.services.issuer import _configured_issuer, _issuer_copy
from apps.invoice.services.issuing import AUDIT_MESSAGES, GENERAL_REGIME, _issue, _issued_notice, _line_values
from apps.invoice.services.numbering import series_of_year
from apps.invoice.services.recipient import _recipient
from apps.invoice.services.writes import _result, _today
from apps.sale import pricing
from apps.sale.models.orders import OrderLine
from apps.sale.models.sales import Sale
from apps.sale.models.settings import Settings
from apps.sale.queries.sales import find_sale
from apps.tax.models import TaxRule
from apps.tax.queries.calculation import round_half_up
from apps.tax.queries.jurisdiction import business_tax_kind, tax_kind_of
from base.services.failed_events import resend_done

#: VeriFactu's DescripcionOperacion of a document born of a sale, in the tax agency's language.
SALE_OPERATION = _("Sale %(number)s")


#: Sales' operation that gives a sale waiting for its document that document (its WORKBOOK, «A qué reacciona»),
#: called by name inside the issue's own transaction (INVOICE-F06); its permission is the platform's.
SALE_RECORD_INVOICE = "sale.sale.record_invoice"


#: The language a document's own texts are written in for the tax agency (DescripcionOperacion).
FISCAL_LANGUAGE = "es"


_CENT_HUNDREDTHS = Decimal("0.01")


def _sale_operation(sale: Sale) -> str:
    """VeriFactu's DescripcionOperacion of a document born of ``sale``, in the tax agency's language."""
    with translation.override(FISCAL_LANGUAGE):
        return str(SALE_OPERATION) % {"number": sale.number}


def _charged_kind(line) -> str:
    """The tax family of the territory a sale line was charged in, as the line froze it (TAX-F11); the
    business's when the line kept no country."""
    if line.tax_country_code:
        return tax_kind_of(line.tax_country_code, line.tax_region_code)
    return business_tax_kind()


def _sale_key(line, rules: dict) -> fiscal.FiscalKey:
    """The fiscal key a sale line was charged with: its frozen root rule and its components; without its
    rule, the tax family of the territory the line was charged in, never a fixed VAT."""
    components = line.tax_components or []
    main = Decimal(str(components[0]["rate_pct"])) if components else line.tax_rate
    surcharge = sum((Decimal(str(c["rate_pct"])) for c in components[1:]), Decimal(0))
    rule = rules.get(line.tax_rule_id)
    if rule is None:
        return fiscal.FiscalKey(
            tax=_charged_kind(line),
            regime=GENERAL_REGIME,
            cls="subject",
            exempt_reason="",
            rate=main,
            surcharge_rate=surcharge,
        )
    exempt = (
        rule.exempt_reason.upper()
        if rule.operation_class == TaxRule.OperationClass.EXEMPT
        else ""
    )
    return fiscal.FiscalKey(
        tax=rule.tax_type or _charged_kind(line),
        regime=rule.regime_key or GENERAL_REGIME,
        cls=rule.operation_class,
        exempt_reason=exempt,
        rate=main,
        surcharge_rate=surcharge,
    )


def _undiscounted(sale_line, order_line: OrderLine | None) -> int:
    """What a charged line was worth at its own price before any discount, in the sale's price mode (with
    or without VAT); a comp or a line a voucher pays was worth nothing to begin with."""
    if sale_line.is_gift or sale_line.voucher_session_id is not None:
        return 0
    if order_line is not None:
        ratio = pricing.price_ratio(
            sale_line.quantity,
            (order_line.unit_factor_num, order_line.unit_factor_den),
            (order_line.pricing_factor_num, order_line.pricing_factor_den),
            sale_line.price_quantity,
        )
    else:
        ratio = Fraction(sale_line.quantity) / Fraction(sale_line.price_quantity)
    return pricing.line_amount(sale_line.unit_price, ratio)


def _net_price(
    line: fiscal.Line, quantity: Decimal, undiscounted: int, *, tax_included: bool
) -> tuple[Decimal, int]:
    """The unit price WITHOUT VAT and before any discount (cents with two decimals) and the discount
    without VAT of a charged line (RD 1619/2012 art. 6.1.f): what it was worth at its own price, without
    VAT in the same proportion the line was charged (or by its key's rates when it came to nothing)."""
    charged = line.total if tax_included else line.base
    if undiscounted <= charged:
        return (Decimal(line.base) / quantity).quantize(_CENT_HUNDREDTHS, ROUND_HALF_UP), 0
    if not tax_included:
        net = Decimal(undiscounted)
    elif line.total:
        net = Decimal(undiscounted) * Decimal(line.base) / Decimal(line.total)
    else:
        rates = Decimal(100) + line.key.rate + line.key.surcharge_rate
        net = Decimal(undiscounted) * Decimal(100) / rates
    unit = (net / quantity).quantize(_CENT_HUNDREDTHS, ROUND_HALF_UP)
    return unit, max(round_half_up(quantity * unit) - line.base, 0)


@operation(
    "invoice.invoice.create_from_sale",
    kind="command",
    permission="invoice.add_invoice",
    input=FromSaleIn,
    output=IssueOut,
    ai={
        "asks": {
            "en": (
                "issue the ticket of sale 20261103-0012 now",
                "sale 20261103-0012 has no invoice yet: issue it",
            ),
            "es": (
                "emite ya el tique de la venta 20261103-0012",
                "la venta 20261103-0012 se quedó sin factura: hazla",
            ),
        },
        "description": "Issue the fiscal document of a charged sale (by its id or its number of the day): its ticket "
        "(F2) or, if it was charged as an invoice, its full invoice (F1) with the customer's data. Read from the sale "
        "itself, born paid. It is also what happens by itself after every charge; asking again issues nothing.",
        "risk": "high",
    },
)
def create_from_sale(ctx: OperationContext, data: FromSaleIn) -> dict:
    sale = find_sale(data.sale_id, data.sale, lock=True)
    existing = Invoice.objects.filter(
        source_sale=sale, source_type=Invoice.Source.SALE
    ).first()
    if existing is not None:
        _tell_sales(ctx, existing, sale.invoice_status)
        return _result(ctx, existing, issued=False, already=True)
    issuer = _configured_issuer()
    full = sale.document_type == Settings.DocumentType.INVOICE
    sale_lines = list(sale.lines.order_by("position", "id"))
    rules = TaxRule.objects.in_bulk(
        {line.tax_rule_id for line in sale_lines if line.tax_rule_id}
    )
    lines = [
        fiscal.Line(
            key=_sale_key(line, rules),
            base=line.net_amount,
            tax=line.tax_amount,
            total=line.line_total,
            category=line.tax_category_key,
        )
        for line in sale_lines
    ]
    closed = fiscal.close_charged(lines, tax_included=sale.tax_included)
    if closed.total != sale.total:
        raise Conflict(
            str(AUDIT_MESSAGES["invoice.totals_mismatch"]),
            code="invoice.totals_mismatch",
        )
    recipient = _recipient(
        ctx,
        data,
        full=full,
        fallback_name=sale.customer_name,
        card=sale.customer,
    )
    series = series_of_year(FULL if full else TICKET, _today().year, ctx)
    order_lines = OrderLine.objects.in_bulk(
        {line.order_line_id for line in sale_lines if line.order_line_id}
    )
    values = []
    for line, sale_line in zip(closed.lines, sale_lines, strict=True):
        unit, discount = _net_price(
            line,
            sale_line.quantity,
            _undiscounted(sale_line, order_lines.get(sale_line.order_line_id)),
            tax_included=sale.tax_included,
        )
        values.append(
            _line_values(
                line,
                description=sale_line.name,
                quantity=sale_line.quantity,
                unit_price=unit,
                discount_amount=discount,
                tax_category_key=sale_line.tax_category_key,
                product_id=sale_line.product_id,
                sale_line_id=sale_line.id,
            )
        )
    invoice = _issue(
        ctx,
        series=series,
        invoice_type="F1" if full else "F2",
        entries=closed.entries,
        lines=values,
        tolerance=closed.tolerance,
        recipient=recipient,
        issuer=_issuer_copy(issuer),
        operation_date=sale.business_day,
        source_type=Invoice.Source.SALE,
        source_sale=sale,
        status=Invoice.Status.PAID,
        paid_at=sale.created_at,
        currency=sale.currency,
        description=_sale_operation(sale),
    )
    _tell_sales(ctx, invoice, sale.invoice_status)
    return _result(ctx, invoice, issued=True)


def _tell_sales(ctx: OperationContext, invoice: Invoice, written: str) -> None:
    """Gives Sales, by its operation, the document of a charge, a void or a refund that was written without
    it and waits (INVOICE-F06) — asked later by the API, the assistant, «Issue now» or the relay —, so the
    sale and its document agree when the issue commits. ``written`` is the fiscal status Sales keeps for that
    document: blank while Sales' own write is still running (the charge, the void or the refund writes the
    answer itself). Sales changes nothing for a document it already has, nor when the relay hands it the
    notice afterwards. The write's event for Invoicing, if the relay gave it up, is resent: it finds it done."""
    if not written:
        return
    record = get_operation(SALE_RECORD_INVOICE)
    as_platform = replace(ctx, permissions=ctx.permissions | {record.permission})
    record(as_platform, record.input.model_validate(_issued_notice(invoice)))
    event, match = _write_event(invoice)
    resend_done(ctx, app_label=Invoice._meta.app_label, event=event, match=match)


def _write_event(invoice: Invoice) -> tuple[str, dict]:
    """The Sales event that asked Invoicing for ``invoice`` and what its payload names: the refund, or the sale."""
    if invoice.source_type == Invoice.Source.REFUND:
        return events.SALE_REFUNDED, {"refund_id": str(invoice.source_refund_id)}
    if invoice.source_type == Invoice.Source.VOID:
        return events.SALE_VOIDED, {"sale_id": str(invoice.source_sale_id)}
    return events.SALE_COMPLETED, {"sale_id": str(invoice.source_sale_id)}
