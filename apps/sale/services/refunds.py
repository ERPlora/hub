"""Refunding a charged sale, whole or in part: its lines, its payments and a voucher's session."""

from decimal import Decimal

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, atomic, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import PaymentMethod, Refund, RefundLine, RefundPayment, Sale, SaleLine
from apps.sale.queries.business import actor, money_text
from apps.sale.queries.other_apps import call_services
from apps.sale.queries.payment_methods import held_methods, method_display_name
from apps.sale.queries.refunds import tender_options
from apps.sale.queries.sales import find_sale, returned_by_line, sessions_to_return
from apps.sale.schemas import RefundIn, RefundOut
from apps.sale.services.checkout import KEY_REUSED
from apps.sale.services.documents import _fiscal_document, _issue_waiting_document

REFUND_REQUIRES_COMPLETED = _("There is no money left to refund on this sale.")
REFUND_TENDER_UNKNOWN = _("That payment is not one of this sale's.")
REFUND_TENDER_DUPLICATED = _("Each payment of the sale can be named only once.")
REFUND_EXCEEDS_TENDER = _(
    "%(method)s: %(amount)s is more than the %(remaining)s left to refund."
)
REFUND_NOT_ELIGIBLE = _("%(method)s: choose how this money goes back.")
REFUND_METHOD_UNAVAILABLE = _("That payment method is not available in this business.")
REFUND_LINE_UNKNOWN = _("That line is not one of this sale's.")
REFUND_LINE_DUPLICATED = _("Each line of the sale can be named only once.")
REFUND_LINE_ALREADY_RETURNED = _(
    "One of the lines marked already came back with another refund. Open the refund again to see what is left."
)
REFUND_LINE_QUANTITY_EXCEEDED = _(
    "One of the lines marked has fewer units left to return: another refund took part of them. Open the refund again "
    "to see what is left."
)
REFUND_IN_PROGRESS = _(
    "This refund is already being recorded. Check the sale before refunding again."
)
REFUND_NOTHING = _("A refund has to give back money or the session of a voucher.")
REFUND_VOUCHER_LINE_WHOLE = _(
    "A line paid with a voucher goes back whole: its session is not split."
)


def _refund_lines(sale: Sale, data: RefundIn) -> list[tuple[SaleLine, Decimal]]:
    lines = {line.id: line for line in sale.lines.all()}
    returned = returned_by_line(sale)
    chosen, seen = [], set()
    for item in data.lines:
        line = lines.get(item.line_id)
        if line is None:
            raise Conflict(str(REFUND_LINE_UNKNOWN), code="sale.refund_line_unknown")
        if item.line_id in seen:
            raise Conflict(
                str(REFUND_LINE_DUPLICATED), code="sale.refund_line_duplicated"
            )
        seen.add(item.line_id)
        left = line.quantity - returned.get(line.id, Decimal(0))
        if left <= 0:
            raise Conflict(
                str(REFUND_LINE_ALREADY_RETURNED),
                code="sale.refund_line_already_returned",
            )
        quantity = item.quantity if item.quantity is not None else left
        if quantity > left:
            raise Conflict(
                str(REFUND_LINE_QUANTITY_EXCEEDED),
                code="sale.refund_line_quantity_exceeded",
            )
        if line.voucher_session_id is not None and quantity != left:
            raise Conflict(
                str(REFUND_VOUCHER_LINE_WHOLE), code="sale.refund_voucher_line_whole"
            )
        chosen.append((line, quantity))
    return chosen


def _refund_legs(sale: Sale, data: RefundIn) -> list[dict]:
    options = {row["payment_id"]: row for row in tender_options(sale)}
    payments = {
        payment.id: payment for payment in sale.payments.select_related("method")
    }
    legs, seen = [], set()
    for allocation in data.allocations:
        option = options.get(allocation.payment_id)
        if option is None:
            raise Conflict(
                str(REFUND_TENDER_UNKNOWN), code="sale.refund_tender_unknown"
            )
        if allocation.payment_id in seen:
            raise Conflict(
                str(REFUND_TENDER_DUPLICATED), code="sale.refund_tender_duplicated"
            )
        seen.add(allocation.payment_id)
        name = method_display_name(option["method_name"])
        if allocation.amount > option["remaining"]:
            message = str(REFUND_EXCEEDS_TENDER) % {
                "method": name,
                "amount": money_text(allocation.amount, sale.currency),
                "remaining": money_text(option["remaining"], sale.currency),
            }
            raise Conflict(message, code="sale.refund_exceeds_tender")
        if allocation.to_method_id is None:
            if not option["refundable"]:
                raise Conflict(
                    str(REFUND_NOT_ELIGIBLE) % {"method": name},
                    code="sale.refund_tender_not_eligible",
                )
            method = payments[allocation.payment_id].method
        else:
            method = PaymentMethod.objects.filter(
                pk=allocation.to_method_id, is_active=True
            ).first()
            if method is None:
                raise Conflict(
                    str(REFUND_METHOD_UNAVAILABLE),
                    code="sale.refund_method_unavailable",
                )
        legs.append(
            {
                "payment": payments[allocation.payment_id],
                "method": method,
                "amount": allocation.amount,
            }
        )
    # Held until the refund ends: one deleted since it was read is not available, as one never added.
    named = {leg["method"].id for leg in legs}
    if held_methods(named) != named:
        raise Conflict(
            str(REFUND_METHOD_UNAVAILABLE), code="sale.refund_method_unavailable"
        )
    return legs


def _refund_replay(data: RefundIn) -> dict | None:
    """The refund this attempt already recorded, if any (``already``); 409 when the key was used for
    another sale or other lines."""
    if not data.idempotency_key:
        return None
    existing = Refund.objects.select_related("sale").filter(idempotency_key=data.idempotency_key).first()
    if existing is None:
        return None
    same_sale = existing.sale_id == data.sale_id if data.sale_id is not None else existing.sale.number == (data.sale or "").strip()
    same_lines = set(existing.lines.values_list("sale_line_id", flat=True)) == {line.line_id for line in data.lines}
    if not (same_sale and same_lines):
        raise Conflict(str(KEY_REUSED), code="sale.idempotency_key_reused")
    return {
        "already": True,
        "refund_id": existing.id,
        "sale_id": existing.sale_id,
        "total": existing.total,
        "fully_refunded": existing.sale.status == Sale.Status.REFUNDED,
        "invoice_status": existing.invoice_status,
        "invoice_number": existing.invoice_number,
        "invoice_type": existing.invoice_type,
    }


@operation(
    "sale.sale.refund",
    kind="command",
    permission="sale.refund_sale",
    input=RefundIn,
    output=RefundOut,
    ai=AI(
        description="Refund a charged sale (by its id or number), whole or in part, with a mandatory reason: how much goes "
        "back on each of its tenders (never more than each charged minus what it already returned; another method if the "
        "original is gone) and, if the customer returns them, which lines and how many units. If no number was given, "
        "find the sale with sale.sale.list. Read sale.refund.options first for its tender and line ids; never ask the "
        "person for internal ids. A line paid with a voucher gives its session back, also with no money at all. Send an "
        "idempotency_key on a retry.",
        risk="high",
        asks={
            "en": (
                "refund the last sale",
                "give back 5 euros of ticket 7, the coffee was cold",
                "she brought one shirt back, refund it",
            ),
            "es": (
                "devuélvele el dinero de la última venta",
                "devuelve 5 € del ticket 7, que el café estaba frío",
                "ha devuelto un producto, hazle el reembolso",
            ),
        },
    ),
)
def refund(ctx: OperationContext, data: RefundIn) -> dict:
    answer = _refund_replay(data)
    if answer is not None:
        return answer
    sale = find_sale(data.sale_id, data.sale, lock=True)
    # The same attempt may have refunded this sale while this one waited for its lock.
    answer = _refund_replay(data)
    if answer is not None:
        return answer
    if sale.status != Sale.Status.COMPLETED:
        raise Conflict(
            str(REFUND_REQUIRES_COMPLETED), code="sale.refund_requires_completed"
        )
    returning = _refund_lines(sale, data)
    legs = _refund_legs(sale, data)
    total = sum(leg["amount"] for leg in legs)
    sessions = [line.voucher_session_id for line, _quantity in returning if line.voucher_session_id]
    if not legs and not sessions:
        raise Conflict(str(REFUND_NOTHING), code="sale.refund_nothing")
    try:
        with atomic():
            record = Refund.objects.create(
                sale=sale,
                total=total,
                reason=data.reason,
                note=data.note,
                idempotency_key=data.idempotency_key,
                created_by=actor(ctx),
            )
    except IntegrityError:
        raise Conflict(
            str(REFUND_IN_PROGRESS), code="sale.refund_in_progress"
        ) from None
    RefundPayment.objects.bulk_create(
        [
            RefundPayment(
                refund=record,
                position=position,
                sale_payment=leg["payment"],
                method=leg["method"],
                method_name=leg["method"].name,
                method_type=leg["method"].type,
                amount=leg["amount"],
            )
            for position, leg in enumerate(legs, start=1)
        ]
    )
    RefundLine.objects.bulk_create(
        [
            RefundLine(refund=record, sale_line=line, quantity=quantity)
            for line, quantity in returning
        ]
    )
    if sessions:
        call_services(
            ctx,
            "service.session.return",
            {"ids": sessions, "reference": record.id, "reason": data.reason},
        )
    sale.refunded_total += total
    # Refunded whole: all the money back and every voucher session back.
    fully = sale.refunded_total >= sale.total and sessions_to_return(sale) == 0
    if fully:
        sale.status = Sale.Status.REFUNDED
    sale.save(update_fields=["refunded_total", "status"])
    record_event(
        ctx,
        events.SALE_REFUNDED,
        {
            "sale_id": str(sale.id),
            "sale_number": sale.number,
            "refund_id": str(record.id),
            "total": total,
            "reason": record.reason,
            "refunded_by": record.created_by,
            "refunded_at": record.created_at.isoformat(),
            "fully_refunded": fully,
            "document_type": sale.document_type,
            "order_id": str(sale.order_id) if sale.order_id else None,
            "customer_id": str(sale.customer_id) if sale.customer_id else None,
            "payments": [
                {
                    "payment_id": str(leg["payment"].id),
                    "method_id": str(leg["method"].id),
                    "method_name": leg["method"].name,
                    "method_type": leg["method"].type,
                    "amount": leg["amount"],
                }
                for leg in legs
            ],
            # A menu gives back each of its dishes, times the menus that come back (COMBO-F10).
            "lines": [
                {
                    "line_id": str(line.id),
                    "product_id": str(unit["product_id"]) if unit["product_id"] else None,
                    "quantity": f"{unit['quantity'] * quantity:.3f}",
                }
                for line, quantity in returning
                for unit in (
                    line.components or [{"product_id": line.product_id, "quantity": 1}]
                )
            ],
        },
    )
    # Its rectifying invoice, by differences or whole, in this very transaction (INVOICE-F09, F10), once
    # the document it rectifies exists: a ticket that waited is asked for first.
    _issue_waiting_document(ctx, sale)
    document = _fiscal_document(
        ctx, "invoice.invoice.rectify_from_refund", {"refund_id": str(record.id)}
    )
    record.invoice_status, record.invoice_number = document["status"], document["number"]
    record.invoice_type = document["type"]
    record.save(update_fields=["invoice_status", "invoice_number", "invoice_type"])
    return {
        "already": False,
        "refund_id": record.id,
        "sale_id": sale.id,
        "total": total,
        "fully_refunded": fully,
        "invoice_status": record.invoice_status,
        "invoice_number": record.invoice_number,
        "invoice_type": record.invoice_type,
    }
