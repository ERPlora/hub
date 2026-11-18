"""Charging an open check or a counter sale: its number, its replay and the sale itself, in one transaction."""

import datetime as dt

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, atomic, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Order, OrderLine, Sale, SaleCounter, SaleLine, SalePayment, Settings, sale_number
from apps.sale.queries import (
    LIMITS_CURRENCY,
    Booking,
    ORDER_CHANGED,
    TICKET_LIMIT,
    actor,
    breakdown_rows,
    business_country,
    business_currency,
    call_services,
    charge_parts,
    current_settings,
    find_order,
    lines_to_charge,
    loose_lines,
    money_text,
    operation_total,
    refresh_combos,
    sale_detail,
    valuate,
)
from apps.sale.schemas import CompleteIn, SaleOut
from apps.sale.services.charge_validation import (
    _check_discounts,
    _check_drawer,
    _checked_country,
    _checked_tax_id,
    _customer_details,
    _legs,
    _served_by,
)
from apps.sale.services.documents import RECIPIENT_KEYS, _fiscal_document, _issue_waiting_document
from apps.sale.services.orders import _recount, _save_lines
from apps.sale.services.printouts import _print_sale
from apps.sale.services.sale_lines import _completed_payload, _sale_lines

CUSTOMER_REQUIRED = _("This business requires a customer on every sale.")
INVOICE_RECIPIENT = _(
    "An invoice needs the customer's name, tax ID and address. Fill them in or charge it as a ticket."
)
TICKET_OVER_LIMIT = _(
    "Above %(limit)s this sale cannot be a ticket: charge it as an invoice with the customer's details."
)
CHECKOUT_IN_PROGRESS = _(
    "This charge is already being recorded. Check it in Sales before charging again."
)
KEY_REUSED = _("That attempt key was already used for another charge. Open it again to charge this one.")


def _number(day: dt.date) -> int:
    """The next number of ``day``: the counter's row raised with ``UPDATE … RETURNING`` (never a sequence)."""
    SaleCounter.objects.bulk_create([SaleCounter(day=day)], ignore_conflicts=True)
    counter = SaleCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


def _replay(ctx: OperationContext, data: CompleteIn) -> dict | None:
    """The sale this attempt already charged, if any (``already``); 409 when the key was charged for
    something else: another check, other lines of it, or a counter sale instead of a check."""
    sale = Sale.objects.select_related("order").filter(idempotency_key=data.idempotency_key).first()
    if sale is None:
        return None
    if data.order_id is None:
        same = sale.order is not None and sale.order.source == Order.Source.COUNTER
    else:
        same = sale.order_id == data.order_id and (
            not data.line_ids or set(sale.order_lines.values_list("id", flat=True)) == set(data.line_ids)
        )
    if not same:
        raise Conflict(str(KEY_REUSED), code="sale.idempotency_key_reused")
    # The same attempt again is the till's retry: a document that waited is asked for once more (no relay issues it on
    # its own); still refused, it keeps waiting, in sight.
    _issue_waiting_document(ctx, sale)
    with translation.override(ctx.language):
        return sale_detail(sale, already=True)


def _claim_counter(ctx: OperationContext, data: CompleteIn) -> Order | dict:
    """A counter sale's check, created FIRST and holding the attempt's key (unique): the same attempt
    sent twice at once waits here, then answers the sale the first one charged."""
    try:
        with atomic():
            return Order.objects.create(
                source=Order.Source.COUNTER,
                attempt_key=data.idempotency_key,
                created_by=actor(ctx),
                appointment_id=data.appointment_id,
            )
    except IntegrityError:
        answer = _replay(ctx, data)
        if answer is None:
            raise Conflict(str(CHECKOUT_IN_PROGRESS), code="sale.checkout_in_progress") from None
        return answer


def _complete(ctx: OperationContext, data: CompleteIn, *, over_limit: bool) -> dict:  # noqa: C901, PLR0912, PLR0915
    answer = _replay(ctx, data)
    if answer is not None:
        return answer
    settings = current_settings()
    card, customer_name, customer_tax_id, customer_address, customer_country = (
        _customer_details(ctx, data)
    )

    if data.order_id is not None:
        order = find_order(data.order_id, lock=True)
        # The same attempt may have charged this check while this one waited for its lock.
        answer = _replay(ctx, data)
        if answer is not None:
            return answer
        if order.status != Order.Status.OPEN or (
            data.order_version is not None and data.order_version != order.version
        ):
            raise Conflict(str(ORDER_CHANGED), code="sale.order_changed")
        lines, closes = lines_to_charge(order, data.line_ids)
        refresh_combos(ctx, lines)
        percent = order.discount_percent
        amount = order.discount_amount if closes else 0
        approved = bool(order.discount_approved_by)
        appointment_id = order.appointment_id
    else:
        claimed = _claim_counter(ctx, data)
        if isinstance(claimed, dict):
            return claimed
        order = claimed
        booking = Booking(data.appointment_id, card.id if card else None)
        lines, closes = (
            loose_lines(
                ctx,
                data.lines,
                data.open_lines,
                data.service_lines,
                booking,
                hold=True,
                combo_lines=data.combo_lines,
            ),
            True,
        )
        percent, amount, approved, appointment_id = (
            data.discount_percent,
            data.discount_amount,
            False,
            data.appointment_id,
        )

    _check_discounts(
        lines,
        percent,
        amount,
        approved=approved,
        over_limit=over_limit,
        settings=settings,
    )
    if settings.require_customer and card is None:
        raise Conflict(str(CUSTOMER_REQUIRED), code="sale.customer_required")
    document_type = data.document_type or settings.default_document_type
    invoice = document_type == Settings.DocumentType.INVOICE
    if invoice and not (customer_name and customer_tax_id and customer_address):
        raise Conflict(str(INVOICE_RECIPIENT), code="sale.invoice_recipient_incomplete")
    if invoice:
        customer_country = _checked_country(customer_country)
        customer_tax_id = _checked_tax_id(
            customer_tax_id, customer_country, data.customer_id_type
        )

    now = timezone.now()
    day = timezone.localdate(now)
    parts = charge_parts(lines)
    valuation = valuate(
        parts,
        discount_percent=percent,
        discount_amount=amount,
        tax_included=settings.default_tax_included,
        on=day,
    )
    country = business_country()
    ticket_limit = TICKET_LIMIT.get(country)
    if (
        document_type == Settings.DocumentType.TICKET
        and ticket_limit is not None
        and valuation.total > ticket_limit
    ):
        raise Conflict(
            str(TICKET_OVER_LIMIT) % {"limit": money_text(ticket_limit, LIMITS_CURRENCY)},
            code="sale.ticket_over_limit",
        )
    counter_sale = order.source == Order.Source.COUNTER and not order.lines.exists()
    operation = operation_total(None if counter_sale else order, closes, valuation, on=day)
    legs = _legs(data, valuation.total, settings, operation)
    _check_drawer(ctx, legs)

    if counter_sale:
        _save_lines(order, lines)
        record_event(
            ctx,
            events.ORDER_OPENED,
            {"order_id": str(order.id), "lines_count": len(lines)},
        )

    served_by = _served_by(ctx, data.staff_id)
    sequence = _number(day)
    principal = max(legs, key=lambda leg: leg["amount"]) if legs else None
    try:
        with atomic():
            sale = Sale.objects.create(
                number=sale_number(day, sequence),
                business_day=day,
                sequence=sequence,
                document_type=document_type,
                order=order,
                customer=card,
                customer_name=customer_name,
                **(
                    {
                        "customer_tax_id": customer_tax_id,
                        "customer_address": customer_address,
                        "customer_country": customer_country,
                        "customer_id_type": data.customer_id_type,
                    }
                    if invoice
                    else {}
                ),
                staff_id=served_by,
                appointment_id=appointment_id,
                tax_included=settings.default_tax_included,
                currency=business_currency(ctx),
                subtotal=valuation.subtotal,
                tax_total=valuation.tax_total,
                discount_percent=percent,
                discount_amount=valuation.discount_amount,
                gift_total=valuation.gift_total,
                total=valuation.total,
                tendered_total=sum(leg["tendered"] for leg in legs),
                change_total=sum(leg["change"] for leg in legs),
                tax_breakdown=breakdown_rows(valuation.breakdown),
                payment_method_name=principal["method"].name if principal else "",
                idempotency_key=data.idempotency_key,
                notes=data.notes,
                created_at=now,
                created_by=actor(ctx),
            )
    except IntegrityError:
        raise Conflict(
            str(CHECKOUT_IN_PROGRESS), code="sale.checkout_in_progress"
        ) from None
    # The sessions held for the lines a voucher pays are delivered with the sale, or nothing is charged; what each
    # is worth from now on stays on its line.
    covered = [line.voucher_session_id for line in lines if line.voucher_session_id]
    session_values = {}
    if covered:
        settled = call_services(
            ctx,
            "service.session.settle",
            {
                "ids": covered,
                "sale_id": sale.id,
                "customer_id": card.id if card else None,
            },
        )
        session_values = {session.id: session.value for session in settled.rows}
    sale_lines = SaleLine.objects.bulk_create(
        _sale_lines(sale, parts, valuation, session_values)
    )
    payments = SalePayment.objects.bulk_create(
        [
            SalePayment(
                sale=sale,
                position=position,
                method=leg["method"],
                method_name=leg["method"].name,
                method_type=leg["method"].type,
                amount=leg["amount"],
                tendered=leg["tendered"],
                change=leg["change"],
                reference=leg["reference"],
            )
            for position, leg in enumerate(legs, start=1)
        ]
    )
    OrderLine.objects.filter(pk__in=[line.id for line in lines]).update(sale=sale)
    if closes:
        order.status = Order.Status.COMPLETED
        order.closed_at = now
    _recount(order)
    order.version = F("version") + 1
    order.save(
        update_fields=[
            "status",
            "closed_at",
            "provisional_total",
            "version",
            "updated_at",
        ]
    )

    completed = _completed_payload(
        sale,
        sale_lines,
        payments,
        customer_tax_id,
        customer_address,
        customer_country,
        data.customer_id_type,
    )
    record_event(ctx, events.SALE_COMPLETED, completed)
    if appointment_id is not None:
        record_event(
            ctx,
            events.SALE_CREATED_FROM_APPOINTMENT,
            {
                "sale_id": str(sale.id),
                "appointment_id": str(appointment_id),
                "staff_id": str(sale.staff_id) if sale.staff_id else None,
                "total": sale.total,
            },
        )
    if closes:
        record_event(ctx, events.ORDER_COMPLETED, {"order_id": str(order.id)})
    # Its ticket (F2) or its invoice (F1), numbered by Invoicing in this very transaction (INVOICE-F01, F02).
    # A ticket's recipient is its card (Invoicing reads it); an invoice's, the one checked above.
    recipient = {key: completed[key] or "" for key in RECIPIENT_KEYS} if invoice else {}
    document = _fiscal_document(
        ctx,
        "invoice.invoice.create_from_sale",
        {"sale_id": str(sale.id), **recipient},
        typed_recipient=invoice,
    )
    sale.invoice_status, sale.invoice_id = document["status"], document["id"]
    sale.invoice_number, sale.invoice_type = document["number"], document["type"]
    sale.save(update_fields=["invoice_status", "invoice_id", "invoice_number", "invoice_type"])
    with translation.override(ctx.language):
        detail = sale_detail(sale)
    # Its receipt (and the drawer's order) to the printing queue, inside this very charge (PRINTING-F07, F13).
    printed = _print_sale(ctx, sale, SaleOut.model_validate(detail), duplicate=False, key=f"sale-{sale.id}-receipt", at_checkout=True)
    return {**detail, "printed": printed}


@operation(
    "sale.sale.complete",
    kind="command",
    permission="sale.take_payment",
    input=CompleteIn,
    output=SaleOut,
    expose_api=True,
    ai=AI(
        description="Charge a sale: an open check (all its lines, or some for a partial charge) or loose lines (products by "
        "SKU or name, services by name, open prices by department). The sessions of the lines paid with a voucher are "
        "spent with it (the sale must be charged to the voucher's owner). Payments: cash with what was handed over (change), card or other "
        "methods for the exact amount, or split. The server prices, taxes and numbers it; a ticket up to 3,000 €, above "
        "or on request an invoice with the customer's name, tax ID and address (ask for them). Send the same "
        "idempotency_key on a retry: it never charges twice.",
        risk="high",
        asks={
            "en": (
                "charge table 4",
                "she paid cash with a 20",
                "card payment for the whole check",
                "half cash, half card",
            ),
            "es": (
                "cóbrale a la mesa 4",
                "cobra en efectivo, me da 20 €",
                "lo paga con tarjeta",
                "la mitad en efectivo y el resto con tarjeta",
            ),
        },
    ),
)
def complete(ctx: OperationContext, data: CompleteIn) -> dict:
    return _complete(ctx, data, over_limit=False)


@operation(
    "sale.sale.complete_over_limit",
    kind="command",
    permission="sale.discount_over_limit",
    input=CompleteIn,
    output=SaleOut,
    ai=AI(
        description="The manager's door to the very same charge as sale.sale.complete, for a discount bigger than the "
        "business's cap. For a named open check, resolve it with sale.order.list(search=...) and charge it directly; "
        "do not stop at sale.order.set_discount_over_limit or ask the person for order_id. Never use it to dodge the "
        "cap when the discount fits under it.",
        risk="high",
        asks={
            "en": (
                "charge it with 50% off, I'm authorising the discount",
                "ring it up with a discount above the cap",
            ),
            "es": (
                "cóbralo con un 50 % de descuento, lo autorizo yo",
                "cobra con el descuento aunque pase del máximo",
            ),
        },
    ),
)
def complete_over_limit(ctx: OperationContext, data: CompleteIn) -> dict:
    return _complete(ctx, data, over_limit=True)
