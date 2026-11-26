"""What the sale does when another app tells it something: a customer merged into another, an invoice issued."""


from live.context import OperationContext
from live.operations import INTERNAL, operation
from live.outbox import record_event

from apps.customer.services.writes import lock_customers
from apps.sale import events
from apps.sale.models.refunds import Refund
from apps.sale.models.sales import FiscalStatus, Sale
from apps.sale.schemas.reactions import CustomerMergedIn, CustomerReassignOut, InvoiceIssuedIn, InvoiceRecordedOut


@operation(
    "sale.customer.reassign",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it, as the reactions run.
    permission="sale.reassign_customer",
    input=CustomerMergedIn,
    output=CustomerReassignOut,
    # When Customers merges two cards, the absorbed card's sales move to the one that stays (the printed name and the
    # amounts never change). Repeating it changes nothing.
    ai=INTERNAL,
)
def reassign_customer(ctx: OperationContext, data: CustomerMergedIn) -> dict:
    moved = 0
    # The card that stays before the sales that move to it; one the Hub admin deleted takes nothing.
    if data.id != data.absorbed_id and lock_customers([data.id]):
        moved = Sale.objects.filter(customer_id=data.absorbed_id).update(
            customer_id=data.id
        )
    if moved:
        record_event(
            ctx,
            events.SALE_REASSIGNED,
            {"customer_id": str(data.id), "absorbed_id": str(data.absorbed_id)},
        )
    return {"customer_id": data.id, "moved": moved}


#: The documents of a charge its paper prints: the ticket or the invoice issued from the sale.
_SALE_DOCUMENTS = {"F1", "F2"}


@operation(
    "sale.sale.record_invoice",
    kind="command",
    # Declared by no role: only the system context (``*``) holds it, as the reactions run.
    permission="sale.record_invoice",
    input=InvoiceIssuedIn,
    output=InvoiceRecordedOut,
    # When Invoicing issues later a document it could not issue in the write itself (no issuer yet…) — the ticket or
    # invoice of a charge, the rectifying invoice of a void or of a refund —, the sale or the refund keeps its number
    # for its paper. Repeating it changes nothing.
    ai=INTERNAL,
)
def record_invoice(ctx: OperationContext, data: InvoiceIssuedIn) -> dict:
    """Links a document issued later to the write it belongs to, by its ``source``: a refund's rectifying
    invoice to that refund, a void's to the sale it voids, the ticket or invoice of a charge to its sale.
    Anything else (a manual invoice, a substitution F3, a rectification of an invoice) is Invoicing's."""
    source, recorded = data.source, 0
    if source is None or source.sale_id is None:
        return {"sale_id": None, "recorded": False}
    issued = {"invoice_status": FiscalStatus.ISSUED, "invoice_number": data.number}
    if source.refund_id is not None:
        recorded = (
            Refund.objects.filter(pk=source.refund_id, sale_id=source.sale_id)
            .exclude(invoice_status=FiscalStatus.ISSUED)
            .update(**issued, invoice_type=data.invoice_type)
        )
    elif source.void:
        recorded = (
            Sale.objects.filter(pk=source.sale_id)
            .exclude(void_invoice_status=FiscalStatus.ISSUED)
            .update(void_invoice_status=FiscalStatus.ISSUED, void_invoice_number=data.number)
        )
    elif source.type == "sale" and data.invoice_type in _SALE_DOCUMENTS:
        recorded = (
            Sale.objects.filter(pk=source.sale_id)
            .exclude(invoice_status=FiscalStatus.ISSUED)
            .update(**issued, invoice_id=data.invoice_id, invoice_type=data.invoice_type)
        )
    if recorded:
        record_event(
            ctx,
            events.SALE_INVOICED,
            {
                "sale_id": str(source.sale_id),
                "invoice_id": str(data.invoice_id),
                "number": data.number,
                "refund_id": str(source.refund_id) if source.refund_id else None,
                "void": source.void,
            },
        )
    return {"sale_id": source.sale_id, "recorded": bool(recorded)}
