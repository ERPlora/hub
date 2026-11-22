"""Paying (INVOICE-F19): an issued invoice marked as paid.
"""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.invoice import events
from apps.invoice.models import Invoice
from apps.invoice.queries import find_invoice
from apps.invoice.schemas import InvoiceOut, MarkPaidIn
from apps.invoice.services.writes import _detail, _now

CANNOT_MARK_PAID = _(
    "This invoice cannot be marked as paid: only an issued invoice that is not paid yet can be. Nothing was "
    "changed."
)


@operation(
    "invoice.invoice.mark_paid",
    kind="command",
    permission="invoice.add_invoice",
    input=MarkPaidIn,
    output=InvoiceOut,
    ai={
        "asks": {
            "en": (
                "mark invoice FACT-2025-000317 as paid",
                "Carpintería Lema has paid their invoice",
                "Fontanería Ortega settled their invoice yesterday",
            ),
            "es": (
                "la factura FACT-2025-000317 ya está pagada",
                "Carpintería Lema ya ha pagado su factura",
                "deja como cobrada la factura de Fontanería Ortega",
                "Fontanería Ortega ya nos ha abonado su factura",
            ),
        },
        "description": "Mark an issued invoice (by its number) as paid now. No amount changes, no payment method is "
        "kept and the till is not touched; a paid, cancelled or rectifying invoice is refused.",
        "risk": "normal",
    },
)
def mark_paid(ctx: OperationContext, data: MarkPaidIn) -> dict:
    invoice = find_invoice(ctx, data.invoice_id, data.number, lock=True)
    if invoice.is_rectification or invoice.status != Invoice.Status.ISSUED:
        raise Conflict(str(CANNOT_MARK_PAID), code="invoice.cannot_mark_paid")
    invoice.status = Invoice.Status.PAID
    invoice.paid_at = _now()
    invoice.save(update_fields=["status", "paid_at", "updated_at"])
    record_event(
        ctx,
        events.INVOICE_PAID,
        {
            "invoice_id": str(invoice.id),
            "number": invoice.number,
            "paid_at": invoice.paid_at.isoformat(),
        },
    )
    return _detail(ctx, invoice)
