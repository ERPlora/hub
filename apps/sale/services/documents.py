"""The fiscal document of a write: Invoicing, by name, in the same transaction."""

import logging

from django.db import DatabaseError
from django.utils import translation
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, OperationError
from live.operations import AI, operation

from apps.sale.models import FiscalStatus, Sale, Settings
from apps.sale.queries.other_apps import call_app
from apps.sale.queries.sales import find_sale, sale_detail
from apps.sale.schemas.sales import SaleOut, SaleRefIn

logger = logging.getLogger(__name__)


#: VeriFactu's refusals (through Invoicing, unchanged) of a business that files for real and cannot reach the AEAT now
#: (verifactu WORKBOOK, «Contrato con Facturación»): not a document that waits but the write's own refusal. Nothing is
#: charged that could never be filed. The route's lacks and the server's (its own certificate it cannot open, no
#: gateway, real filing closed).
NO_WAY_TO_THE_AEAT = frozenset(
    {
        "verifactu.representation_not_approved",
        "verifactu.own_certificate_missing",
        "verifactu.own_certificate_unreadable",
        "verifactu.gateway_unavailable",
        "verifactu.production_closed",
    }
)

#: The keys of ``sale.sale.completed`` that carry the recipient of an invoice (empty, never null).
RECIPIENT_KEYS = (
    "customer_name",
    "customer_tax_id",
    "customer_address",
    "customer_country",
    "customer_id_type",
)


def _fiscal_document(  # noqa: C901
    ctx: OperationContext,
    name: str,
    data: dict,
    *,
    typed_recipient: bool = False,
    strict: bool = False,
) -> dict:
    """Invoicing's operation ``name`` (its ticket or invoice of a charge, its rectifying invoice of a refund or a void),
    run by name with the seller's session INSIDE this write's transaction: the document and its number commit with the
    sale, or neither does.

    ``{status, id, number, type}``: «issued» with the document; «none» when there is nothing to declare
    (a refund of no money); «unavailable» when Invoicing is not in this business (the sale stays a ticket
    without fiscal document); «pending» when Invoicing refused now (no issuer yet, the seller may not
    issue…): its savepoint leaves nothing behind, the write goes on, and Invoicing's own reaction to the
    notice issues it later (INVOICE-F06). A programming error (``LiveMisuse``) is never swallowed. With
    ``typed_recipient`` (a full invoice, whose recipient is the cashier's input), Invoicing refusing that
    input (``InvalidPayload``) is the caller's 422, to fix now: such a document would never be issued. A
    business that files for real and cannot reach the AEAT (``NO_WAY_TO_THE_AEAT``) refuses the write itself:
    nothing is charged. ``strict`` («Issue now»): every refusal reaches the caller as it is, worded by
    Invoicing."""
    try:
        answer = call_app(ctx, name, data, "sale.invoice_unavailable")
    except InvalidPayload:
        if typed_recipient or strict:
            raise
        failure = "invalid_payload"
    except Conflict as refusal:
        if strict or refusal.code in NO_WAY_TO_THE_AEAT:
            raise
        if refusal.code == "sale.invoice_unavailable":
            return {"status": FiscalStatus.UNAVAILABLE, "id": None, "number": "", "type": ""}
        failure = refusal.code
    except OperationError as refusal:
        if strict:
            raise
        failure = refusal.code
    except DatabaseError as error:
        if strict:
            raise
        failure = type(error).__name__
    else:
        document = answer.invoice
        if document is None:
            return {"status": FiscalStatus.NONE, "id": None, "number": "", "type": ""}
        return {
            "status": FiscalStatus.ISSUED,
            "id": document.id,
            "number": document.number,
            "type": document.invoice_type,
        }
    logger.warning("sale: %s refused (%s); Invoicing issues it later from the outbox", name, failure)
    return {"status": FiscalStatus.PENDING, "id": None, "number": "", "type": ""}


def _recipient_of(sale: Sale) -> dict:
    """What a document issued later declares as the recipient: an invoice's, as checked at the till; a
    ticket's is its card, which Invoicing reads itself."""
    if sale.document_type != Settings.DocumentType.INVOICE:
        return {}
    return {
        "customer_name": sale.customer_name,
        "customer_tax_id": sale.customer_tax_id,
        "customer_address": sale.customer_address,
        "customer_country": sale.customer_country,
        "customer_id_type": sale.customer_id_type,
    }


def _issue_waiting_document(ctx: OperationContext, sale: Sale, *, strict: bool = False) -> bool:
    """The ticket or invoice of ``sale`` while it waits (``pending``), asked again by name with the
    recipient the sale keeps: idempotent in Invoicing (one per sale). True when it is issued now; Invoicing
    has then given the sale its document by ``sale.sale.record_invoice``, in this same transaction
    (INVOICE-F06), so the sale is read again, not written twice."""
    if sale.invoice_status != FiscalStatus.PENDING:
        return False
    document = _fiscal_document(
        ctx,
        "invoice.invoice.create_from_sale",
        {"sale_id": str(sale.id), **_recipient_of(sale)},
        strict=strict,
    )
    if document["status"] != FiscalStatus.ISSUED:
        return False
    sale.refresh_from_db(fields=["invoice_status", "invoice_id", "invoice_number", "invoice_type"])
    return True


@operation(
    "sale.sale.issue_documents",
    kind="command",
    permission="sale.take_payment",
    input=SaleRefIn,
    output=SaleOut,
    ai=AI(
        description="Issue now the fiscal documents of a sale (by its id or number) that wait because Invoicing could "
        "not issue them in the charge, the void or a refund (no issuer yet, no permission…): its ticket or invoice, "
        "the rectifying invoice of its void and those of its refunds. If no number was given, find the sale with "
        "sale.sale.list; do not charge it again and never ask for its internal id. A refusal says why and changes "
        "nothing; with nothing waiting, nothing happens.",
        risk="high",
        asks={
            "en": (
                "issue the invoice that got stuck for sale 12",
                "issue the fiscal document that is still pending for that ticket",
            ),
            "es": (
                "emite ya la factura pendiente de la venta 12",
                "saca el tique fiscal que se quedó colgado",
            ),
        },
    ),
)
def issue_documents(ctx: OperationContext, data: SaleRefIn) -> dict:
    """«Issue now» (the relay gives up after its last attempt): every document of the sale that waits, in
    order — its own, then its void's or its refunds' rectifying invoices, which need it —, each by its
    operation of Invoicing with the caller's session. Invoicing gives each one it issues to the sale or the
    refund (``sale.sale.record_invoice``, in this transaction, INVOICE-F06): only an answer with no document
    (nothing left to declare) is written here. Any refusal reaches the caller and nothing is kept."""
    sale = find_sale(data.sale_id, data.sale, lock=True)
    _issue_waiting_document(ctx, sale, strict=True)
    if sale.void_invoice_status == FiscalStatus.PENDING:
        document = _fiscal_document(
            ctx, "invoice.invoice.rectify_from_void", {"sale_id": str(sale.id)}, strict=True
        )
        if document["status"] != FiscalStatus.ISSUED:
            sale.void_invoice_status, sale.void_invoice_number = document["status"], document["number"]
            sale.save(update_fields=["void_invoice_status", "void_invoice_number"])
    for record in sale.refunds.filter(invoice_status=FiscalStatus.PENDING).order_by(
        "created_at", "id"
    ):
        document = _fiscal_document(
            ctx, "invoice.invoice.rectify_from_refund", {"refund_id": str(record.id)}, strict=True
        )
        if document["status"] != FiscalStatus.ISSUED:
            record.invoice_status, record.invoice_number = document["status"], document["number"]
            record.invoice_type = document["type"]
            record.save(update_fields=["invoice_status", "invoice_number", "invoice_type"])
    sale.refresh_from_db()
    with translation.override(ctx.language):
        return sale_detail(sale)
