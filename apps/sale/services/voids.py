"""Voiding a charged sale."""


from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Sale, Settings
from apps.sale.queries.business import actor
from apps.sale.queries.other_apps import call_services
from apps.sale.queries.sales import find_sale, sale_detail
from apps.sale.schemas.sales import SaleOut, VoidIn
from apps.sale.services.documents import _fiscal_document, _issue_waiting_document

ALREADY_VOIDED = _("This sale is already voided.")
ALREADY_REFUNDED = _(
    "This sale already has refunds: refund what is left instead of voiding it."
)
REQUIRES_CREDIT_NOTE = _(
    "This sale carries a full invoice: issue a credit note instead of voiding it."
)


@operation(
    "sale.sale.void",
    kind="command",
    permission="sale.void_sale",
    input=VoidIn,
    output=SaleOut,
    ai=AI(
        description="Void a charged sale (by its id or number) with a mandatory reason, before any money went back: it is "
        "kept, marked voided with who, when and why, the sessions of the vouchers it spent go back, and stock and the "
        "customer's history are corrected. A sale with "
        "refunds is refunded instead; one charged as a full invoice is corrected with a credit note.",
        risk="high",
        asks={
            "en": (
                "void the last sale, I charged it twice",
                "void ticket 12, wrong table",
            ),
            "es": (
                "anula la última venta, la cobré dos veces",
                "anula el ticket 12, que me equivoqué de mesa",
            ),
        },
    ),
)
def void_sale(ctx: OperationContext, data: VoidIn) -> dict:
    sale = find_sale(data.sale_id, data.sale, lock=True)
    if sale.status == Sale.Status.REFUNDED:
        raise Conflict(str(ALREADY_REFUNDED), code="sale.sale_already_refunded")
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(str(ALREADY_VOIDED), code="sale.already_voided")
    if sale.document_type == Settings.DocumentType.INVOICE:
        raise Conflict(str(REQUIRES_CREDIT_NOTE), code="sale.void_requires_credit_note")
    if sale.refunded_total > 0 or sale.refunds.exists():
        raise Conflict(str(ALREADY_REFUNDED), code="sale.sale_already_refunded")
    # A ticket that waited is issued first: its rectifying invoice needs it (INVOICE-F07). Still refused,
    # both wait in sight and the void goes on.
    _issue_waiting_document(ctx, sale)
    # Every session spent in it goes back to its voucher (SERVICE-F27), or nothing is voided.
    sessions = list(
        sale.lines.exclude(voucher_session_id=None).values_list(
            "voucher_session_id", flat=True
        )
    )
    if sessions:
        call_services(
            ctx,
            "service.session.return",
            {"ids": sessions, "reference": sale.id, "reason": data.reason},
        )
    sale.status = Sale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.voided_by = actor(ctx)
    sale.void_reason = data.reason
    sale.notes = f"{sale.notes}\n[VOIDED] {data.reason}".strip()
    sale.save(
        update_fields=["status", "voided_at", "voided_by", "void_reason", "notes"]
    )
    record_event(
        ctx,
        events.SALE_VOIDED,
        {
            "sale_id": str(sale.id),
            "sale_number": sale.number,
            "reason": sale.void_reason,
            "voided_by": sale.voided_by,
            "voided_at": sale.voided_at.isoformat(),
            "total": sale.total,
            "order_id": str(sale.order_id) if sale.order_id else None,
            "document_type": sale.document_type,
            "customer_id": str(sale.customer_id) if sale.customer_id else None,
        },
    )
    # The rectifying invoice of the whole ticket (R5), in this very transaction (INVOICE-F07).
    document = _fiscal_document(
        ctx, "invoice.invoice.rectify_from_void", {"sale_id": str(sale.id)}
    )
    sale.void_invoice_status, sale.void_invoice_number = document["status"], document["number"]
    sale.save(update_fields=["void_invoice_status", "void_invoice_number"])
    with translation.override(ctx.language):
        return sale_detail(sale)
