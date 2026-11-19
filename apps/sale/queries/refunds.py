"""The refunds of a sale and what is left to refund of it."""

from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import translation
from live.context import OperationContext
from live.operations import AI, operation

from apps.sale.models import Refund, Sale
from apps.sale.queries.payment_methods import method_display_name
from apps.sale.queries.sales import find_sale, returned_by_line
from apps.sale.schemas import RefundByKeyIn, RefundByKeyOut, RefundListOut, RefundOptionsOut, SaleRefIn
from base.business import currency_decimals


def tender_options(sale: Sale) -> list[dict]:
    """One row per tender of ``sale``, always: what it charged, gave back and has left, and whether
    the money can go back through its own method."""
    rows = []
    for payment in sale.payments.select_related("method").order_by("position", "id"):
        refunded = payment.refunds.aggregate(total=Coalesce(Sum("amount"), 0))["total"]
        remaining = payment.amount - refunded
        if remaining <= 0:
            refundable, reason = False, "already_refunded"
        elif not payment.method.is_active:
            refundable, reason = False, "method_unavailable"
        else:
            refundable, reason = True, ""
        rows.append(
            {
                "payment_id": payment.id,
                "position": payment.position,
                "method_id": payment.method_id,
                "method_name": method_display_name(payment.method_name),
                "method_type": payment.method_type,
                "charged": payment.amount,
                "refunded": refunded,
                "remaining": remaining,
                "refundable": refundable,
                "reason": reason,
            }
        )
    return rows


@operation(
    "sale.refund.options",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=RefundOptionsOut,
    expose_api=True,
    ai=AI(
        description="Refund options: what a sale can still give back, for each tender and each line. For each tender, "
        "what it charged, what it already returned, what is left and whether it can go back through its own method; "
        "for each line, the units already returned and left. Use this read before sale.sale.refund. If no sale number "
        "was given, find the sale with sale.sale.list; never ask the person for its internal id.",
        asks={
            "en": (
                "how much can I still give back on that sale?",
                "what's left to refund on ticket 12?",
            ),
            "es": (
                "¿cuánto se puede devolver todavía de esa venta?",
                "¿qué queda por devolver del ticket 12?",
            ),
        },
    ),
)
def refund_options(ctx: OperationContext, params: SaleRefIn) -> dict:
    sale = find_sale(params.sale_id, params.sale)
    returned = returned_by_line(sale)
    with translation.override(ctx.language):
        return {
            "sale_id": sale.id,
            "number": sale.number,
            "status": sale.status,
            "currency": sale.currency,
            "currency_decimals": currency_decimals(sale.currency),
            "total": sale.total,
            "refunded_total": sale.refunded_total,
            "refundable_total": sale.refundable_total,
            "tenders": tender_options(sale),
            "lines": [
                {
                    "line_id": line.id,
                    "name": line.name,
                    "unit": line.unit,
                    "quantity": line.quantity,
                    "returned": returned.get(line.id, Decimal(0)),
                    "left": line.quantity - returned.get(line.id, Decimal(0)),
                    "line_total": line.line_total,
                    "is_gift": line.is_gift,
                    "paid_by_voucher": line.paid_by_voucher,
                    "voucher_name": line.voucher_name,
                }
                for line in sale.lines.order_by("position", "id")
            ],
        }


def refund_row(refund: Refund) -> dict:
    return {
        "id": refund.id,
        "sale_id": refund.sale_id,
        "total": refund.total,
        "reason": refund.reason,
        "note": refund.note,
        "created_at": refund.created_at,
        "created_by": refund.created_by,
        "invoice_status": refund.invoice_status,
        "invoice_number": refund.invoice_number,
        "invoice_type": refund.invoice_type,
    }


@operation(
    "sale.refund.list",
    kind="query",
    permission="sale.view_sale",
    input=SaleRefIn,
    output=RefundListOut,
    expose_api=True,
    ai=AI(
        description="List the refunds of a sale, newest first, with their amount, reason and who made them. If no sale "
        "number was given, find the sale with sale.sale.list rather than looking through open checks; never ask the "
        "person for its internal id.",
        asks={
            "en": (
                "what refunds did that sale have?",
                "who gave money back on ticket 7?",
            ),
            "es": (
                "¿qué devoluciones tiene esa venta?",
                "¿quién hizo la devolución del ticket 7?",
            ),
        },
    ),
)
def list_refunds(ctx: OperationContext, params: SaleRefIn) -> dict:
    sale = find_sale(params.sale_id, params.sale)
    return {
        "rows": [
            refund_row(refund) for refund in sale.refunds.order_by("-created_at", "-id")
        ]
    }


@operation(
    "sale.refund.by_idempotency_key",
    kind="query",
    permission="sale.view_sale",
    input=RefundByKeyIn,
    output=RefundByKeyOut,
    expose_api=True,
    ai=AI(
        description="Find the refund recorded with a refund attempt's key, so a retry recovers it instead of refunding twice.",
        asks={
            "en": (
                "the refund froze halfway, did it go through?",
                "was that refund saved or do I do it again?",
            ),
            "es": (
                "se cortó al devolver, ¿se hizo la devolución?",
                "¿quedó hecha la devolución que se colgó?",
            ),
        },
    ),
)
def refund_by_key(ctx: OperationContext, params: RefundByKeyIn) -> dict:
    refund = Refund.objects.filter(idempotency_key=params.idempotency_key).first()
    return {
        "found": refund is not None,
        "refund": refund_row(refund) if refund else None,
    }
