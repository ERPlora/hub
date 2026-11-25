"""How a document is read: ``invoice_row`` and ``invoice_detail`` are the one way a document becomes an output (the
lists, the detail, the document of a sale and every write answer with them), ``find_invoice`` finds it among the ones
the caller sees and ``document_of_sale`` finds the document in force of a sale.
"""

from babel.numbers import get_currency_precision
from django.db.models import Count, Exists, OuterRef, Prefetch, Sum
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound

from apps.invoice.document_issuer import document_issuer
from apps.invoice.models import Invoice, InvoiceLine
from apps.invoice.queries.overdue import is_overdue
from apps.invoice.queries.ownership import INVOICES

INVOICE_NOT_FOUND = _("Invoice not found.")


def with_links(invoices):
    """The queryset with what a row says about its links (the rectified number, a replaced ticket)."""
    return invoices.select_related("rectifies").annotate(
        substituted_flag=Exists(Invoice.objects.filter(substitutes=OuterRef("pk"))),
        rectification_count=Count("rectifications", distinct=True),
    )


def _flags(invoice: Invoice, *, substituted: bool, rectified: bool) -> dict:
    """What can still be done to a document, and whether it is overdue: the row and the detail ask the same questions."""
    ordinary = not invoice.is_rectification
    # erplora.com corrects the ones it issued.
    by_hand = invoice.platform_ref is None
    return {
        "substituted": substituted,
        "overdue": is_overdue(invoice, substituted=substituted),
        "can_mark_paid": ordinary and invoice.status == Invoice.Status.ISSUED,
        "can_rectify": by_hand
        and ordinary
        and invoice.status != Invoice.Status.CANCELLED
        and not substituted,
        "can_substitute": by_hand
        and invoice.invoice_type == "F2"
        and invoice.status != Invoice.Status.CANCELLED
        and not substituted
        and not rectified,
    }


def invoice_row(invoice: Invoice) -> dict:
    """An ``InvoiceRowOut`` (best through ``with_links``)."""
    substituted = getattr(invoice, "substituted_flag", None)
    if substituted is None:
        substituted = invoice.substitutions.exists()
    count = getattr(invoice, "rectification_count", None)
    rectified = invoice.rectifications.exists() if count is None else count > 0
    return {
        "id": invoice.id,
        "number": invoice.number,
        "invoice_type": invoice.invoice_type,
        "series_code": invoice.series_code,
        "year": invoice.year,
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "issued_at": invoice.issued_at,
        "customer_name": invoice.customer_name,
        "customer_tax_id": invoice.customer_tax_id,
        "base_amount": invoice.base_amount,
        "tax_amount": invoice.tax_amount,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "currency_decimals": get_currency_precision(invoice.currency),
        "status": invoice.status,
        "source_type": invoice.source_type,
        "rectifies_id": invoice.rectifies_id,
        "rectifies_number": invoice.rectifies.number if invoice.rectifies_id else "",
        **_flags(invoice, substituted=substituted, rectified=rectified),
    }


def _link(invoice: Invoice | None) -> dict | None:
    if invoice is None:
        return None
    return {
        "id": invoice.id,
        "number": invoice.number,
        "invoice_type": invoice.invoice_type,
        "status": invoice.status,
        "issue_date": invoice.issue_date,
        "total_amount": invoice.total_amount,
    }


def _line(line: InvoiceLine) -> dict:
    return {
        "id": line.id,
        "position": line.position,
        "description": line.description,
        "quantity": line.quantity,
        "unit_price": line.unit_price,
        "discount_amount": line.discount_amount,
        "tax_rate": line.tax_rate,
        "surcharge_rate": line.surcharge_rate,
        "tax_category_key": line.tax_category_key,
        "base_amount": line.base_amount,
        "tax_amount": line.tax_amount,
        "total_amount": line.total_amount,
        "product_id": line.product_id,
    }


def remaining_of(invoice: Invoice) -> int:
    """What is left of a document after its rectifications (a rectification has nothing left)."""
    if invoice.is_rectification:
        return 0
    taken = invoice.rectifications.aggregate(total=Coalesce(Sum("total_amount"), 0))[
        "total"
    ]
    return invoice.total_amount + taken


def _loaded(invoice: Invoice) -> Invoice:
    return (
        Invoice.objects.select_related("rectifies", "substitutes", "source_sale")
        .prefetch_related(
            Prefetch("lines", queryset=InvoiceLine.objects.order_by("position", "id")),
            Prefetch(
                "rectifications", queryset=Invoice.objects.order_by("issued_at", "id")
            ),
        )
        .get(pk=invoice.pk)
    )


def invoice_detail(invoice: Invoice) -> dict:
    """An ``InvoiceOut``: the document with its lines, its breakdown and its links."""
    invoice = _loaded(invoice)
    substituted_by = Invoice.objects.filter(substitutes=invoice).first()
    rectifications = list(invoice.rectifications.all())
    row = invoice_row(invoice)
    row.update(
        _flags(
            invoice,
            substituted=substituted_by is not None,
            rectified=bool(rectifications),
        )
    )
    return {
        **row,
        "series_id": invoice.series_id,
        "sequence": invoice.sequence,
        "operation_date": invoice.operation_date,
        **document_issuer(invoice),
        "customer_id": invoice.customer_id,
        "customer_address": invoice.customer_address,
        "customer_country": invoice.customer_country,
        "customer_id_type": invoice.customer_id_type,
        "description": invoice.description,
        "notes": invoice.notes,
        "withholding_rate": invoice.withholding_rate,
        "withholding_amount": invoice.withholding_amount,
        "payable_amount": invoice.payable_amount,
        "tax_breakdown": invoice.tax_breakdown,
        "rectification_kind": invoice.rectification_kind,
        "sale_id": invoice.source_sale_id,
        "sale_number": invoice.source_sale.number if invoice.source_sale_id else "",
        "refund_id": invoice.source_refund_id,
        "rectifies": _link(invoice.rectifies),
        "substitutes": _link(invoice.substitutes),
        "substituted_by": _link(substituted_by),
        "rectifications": [_link(item) for item in rectifications],
        "remaining": remaining_of(invoice),
        "paid_at": invoice.paid_at,
        "created_by": invoice.created_by,
        "lines": [_line(line) for line in invoice.lines.all()],
    }


def find_invoice(ctx: OperationContext, invoice_id, number: str | None, *, lock: bool = False) -> Invoice:
    """The document named by its id or its number among the ones the caller sees (``INVOICES``); ``NotFound`` when
    there is none, also for someone else's to a person who sees only theirs."""
    invoices = INVOICES.visible(ctx).select_for_update() if lock else INVOICES.visible(ctx)
    if invoice_id is not None:
        invoice = invoices.filter(pk=invoice_id).first()
    else:
        invoice = invoices.filter(number=(number or "").strip()).order_by("-issued_at", "-id").first()
    if invoice is None:
        raise NotFound(str(INVOICE_NOT_FOUND), code="invoice.not_found")
    return invoice


def document_of_sale(sale_id) -> Invoice | None:
    """The document in force of a sale: the one it was invoiced with, or the full invoice (F3) that
    replaced its ticket. ``None`` while it has none."""
    born = Invoice.objects.filter(
        source_sale_id=sale_id, source_type=Invoice.Source.SALE
    ).first()
    if born is None:
        return None
    return Invoice.objects.filter(substitutes=born).first() or born


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    rows = list(queryset[params.offset : params.offset + params.limit])
    return {
        "rows": [row(item) for item in rows],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }
