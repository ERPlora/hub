"""Writes of the payments: recorded as a draft with their reference of the day, approved, sent, completed and
cancelled. Each step locks the payment's row first and moves it only from its own state."""

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.payment import events
from apps.payment.models import Payment, PaymentCounter
from apps.payment.queries import find_method, find_payment, method_to_pay_from, payment_row
from apps.payment.schemas import CancelIn, PaymentIn, PaymentOut, PaymentRefIn
from apps.payment.services.actor import _actor
from base import operations as platform
from base.assistant import card_order
from base.business import business_zone

APPROVE_REFUSED = _("Only a draft payment can be approved; this one is %(status)s.")
SEND_REFUSED = _(
    "Only an approved payment can be marked as sent; this one is %(status)s."
)
COMPLETE_REFUSED = _(
    "Only a sent payment can be marked as completed; this one is %(status)s."
)
NOT_CANCELLABLE = _("This payment can no longer be cancelled.")
KEY_REUSED = _(
    "That attempt key already recorded another payment. Make a new key for each payment."
)

#: A finished payment admits no step and no cancellation.
FINISHED = (Payment.Status.COMPLETED, Payment.Status.CANCELLED)


# ── Payments ──────────────────────────────────────────────────────────────────────────────────


def _number(day) -> int:
    """The next number of ``day``: the counter's row raised with ``UPDATE … RETURNING``."""
    PaymentCounter.objects.bulk_create([PaymentCounter(day=day)], ignore_conflicts=True)
    counter = PaymentCounter.objects.get(day=day)
    counter.last = F("last") + 1
    counter.save(update_fields=["last"])
    return counter.last


#: What a payment keeps of its attempt: the same attempt sent again carries the same.
ATTEMPT_FIELDS = (
    "payment_date",
    "amount",
    "beneficiary_name",
    "beneficiary_iban",
    "concept",
    "supplier_invoice_ref",
)


def _same_attempt(payment: Payment, data: PaymentIn, currency: str) -> bool:
    if any(getattr(payment, field) != getattr(data, field) for field in ATTEMPT_FIELDS):
        return False
    if payment.currency != currency:
        return False
    if data.method_id is not None:
        return payment.method_id == data.method_id
    try:
        return find_method(None, data.method).pk == payment.method_id
    except (NotFound, Conflict):
        return False


def _recorded(data: PaymentIn, currency: str) -> dict | None:
    """The payment the attempt of ``data`` (in ``currency``) already recorded, as it is now; 409 when its key
    recorded another payment."""
    if data.idempotency_key is None:
        return None
    payment = (
        Payment.objects.select_related("method")
        .filter(idempotency_key=data.idempotency_key)
        .first()
    )
    if payment is None:
        return None
    if not _same_attempt(payment, data, currency):
        raise Conflict(str(KEY_REUSED), code="payment.idempotency_key_reused")
    return payment_row(payment)


@operation(
    "payment.payment.create",
    kind="command",
    permission="payment.add_payment",
    input=PaymentIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "record a 120 € transfer to Makro for their invoice",
                "note down 80 € owed to the electrician as a draft",
            ),
            "es": (
                "apunta una transferencia de 120 € a Makro desde el Sabadell",
                "deja anotados 80 € para el electricista, sin mover dinero",
            ),
        },
        "description": "Record an outgoing payment (to a supplier, a transfer, a refund that is not a sale's) "
        "as a draft, with its reference of the day: the active method it leaves from (by id or name), the "
        "day, the amount in minor units (12,50 € = 1250), the beneficiary and optionally the concept, IBAN, "
        "supplier's invoice and currency. It moves no money. Never use it to charge a customer.",
        "risk": "normal",
        "check": "payment.payment.check",
        "summary": card_order.said_first("beneficiary_name", "supplier_invoice_ref", "amount"),
    },
)
def create_payment(ctx: OperationContext, data: PaymentIn) -> dict:
    # Without one, the business's currency: its country's (BASE-F50), never a euro fixed here.
    currency = data.currency or platform.business_currency(ctx.scope)
    recorded = _recorded(data, currency)
    if recorded is not None:
        return recorded
    method = method_to_pay_from(data, lock=True)
    day = timezone.localdate(timezone=business_zone())
    actor = _actor(ctx)
    try:
        # The number and the row in one savepoint: an attempt that lost the race to its twin gives its
        # number back and answers the twin's payment.
        with atomic():
            payment = Payment.objects.create(
                reference=f"PAY-{day:%Y%m%d}-{_number(day):04d}",
                method=method,
                payment_date=data.payment_date,
                amount=data.amount,
                currency=currency,
                beneficiary_name=data.beneficiary_name,
                beneficiary_iban=data.beneficiary_iban,
                concept=data.concept,
                supplier_invoice_ref=data.supplier_invoice_ref,
                idempotency_key=data.idempotency_key,
                created_by=actor,
                updated_by=actor,
            )
    except IntegrityError:
        recorded = _recorded(data, currency)
        if recorded is None:
            raise
        return recorded
    record_event(
        ctx,
        events.PAYMENT_CREATED,
        {
            "id": str(payment.id),
            "reference": payment.reference,
            "method_id": str(method.id),
            "amount": payment.amount,
            "currency": payment.currency,
            "beneficiary_name": payment.beneficiary_name,
            "payment_date": payment.payment_date.isoformat(),
            "status": payment.status,
        },
    )
    return payment_row(payment)


def _move(
    ctx: OperationContext,
    payment: Payment,
    status: str,
    event: str,
    **fields,
) -> dict:
    """Moves the locked ``payment`` to ``status`` (with ``fields`` and the step's trail: who and when)
    and records ``event``."""
    actor, now = _actor(ctx), timezone.now()
    trail = {
        Payment.Status.APPROVED: {"approved_by": actor, "approved_at": now},
        Payment.Status.SENT: {"sent_at": now},
        Payment.Status.COMPLETED: {"completed_at": now},
        Payment.Status.CANCELLED: {"cancelled_by": actor, "cancelled_at": now},
    }[status]
    fields = {**fields, **trail}
    payment.status = status
    payment.updated_by = actor
    for field, value in fields.items():
        setattr(payment, field, value)
    payment.save(update_fields=["status", "updated_by", "updated_at", *fields])
    record_event(
        ctx,
        event,
        {
            "id": str(payment.id),
            "reference": payment.reference,
            "status": payment.status,
            "amount": payment.amount,
            "currency": payment.currency,
        },
    )
    return payment_row(payment)


def _step(  # noqa: PLR0913
    ctx: OperationContext,
    data: PaymentRefIn,
    *,
    origin: str,
    target: str,
    refusal,
    event: str,
) -> dict:
    payment = find_payment(data.id, data.reference, lock=True)
    if payment.status != origin:
        raise Conflict(
            str(refusal) % {"status": Payment.Status(payment.status).label},
            code="payment.invalid_transition",
        )
    return _move(ctx, payment, target, event)


@operation(
    "payment.payment.approve",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.approve_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "give the go-ahead to the 120 € draft to Makro",
                "authorise the electrician's transfer",
            ),
            "es": (
                "aprueba el borrador de 120 € a Makro",
                "autoriza la transferencia al electricista",
            ),
        },
        "description": "Approve a draft outgoing payment (named by its id or its reference): it authorises it "
        "to be paid. Only a draft can be approved.",
        "risk": "high",
    },
)
def approve_payment(ctx: OperationContext, data: PaymentRefIn) -> dict:
    return _step(
        ctx,
        data,
        origin=Payment.Status.DRAFT,
        target=Payment.Status.APPROVED,
        refusal=APPROVE_REFUSED,
        event=events.PAYMENT_APPROVED,
    )


@operation(
    "payment.payment.mark_sent",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "I've made the Makro transfer at the bank, mark it as sent",
                "the electrician's money has gone out from the bank",
            ),
            "es": (
                "ya he hecho la transferencia a Makro desde el banco: márcala como enviada",
                "lo del electricista ya ha salido del banco",
            ),
        },
        "description": "Mark an approved outgoing payment as sent to the bank or the beneficiary (named by its "
        "id or its reference). It records what a person did; it sends nothing.",
        "risk": "high",
    },
)
def mark_sent(ctx: OperationContext, data: PaymentRefIn) -> dict:
    return _step(
        ctx,
        data,
        origin=Payment.Status.APPROVED,
        target=Payment.Status.SENT,
        refusal=SEND_REFUSED,
        event=events.PAYMENT_SENT,
    )


@operation(
    "payment.payment.mark_completed",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Makro has received the money, mark it as completed",
                "the electrician's transfer has arrived, that one is done",
            ),
            "es": (
                "Makro ya ha recibido el dinero: dalo por completado",
                "al electricista ya le ha llegado la transferencia",
            ),
        },
        "description": "Mark a sent outgoing payment as completed, once the beneficiary has received it (named "
        "by its id or its reference). It is final.",
        "risk": "high",
    },
)
def mark_completed(ctx: OperationContext, data: PaymentRefIn) -> dict:
    return _step(
        ctx,
        data,
        origin=Payment.Status.SENT,
        target=Payment.Status.COMPLETED,
        refusal=COMPLETE_REFUSED,
        event=events.PAYMENT_COMPLETED,
    )


@operation(
    "payment.payment.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.approve_payment",
    input=CancelIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel the Makro transfer, it was a duplicate",
                "call off the electrician's transfer, we gave him cash",
            ),
            "es": (
                "anula la transferencia a Makro, estaba repetida",
                "cancela lo del electricista porque ya se le dio en efectivo",
            ),
        },
        "description": "Cancel an outgoing payment that is not completed (named by its id or its reference), "
        "with the mandatory reason, which stays on the payment. It cannot be undone: record another one.",
        "risk": "high",
    },
)
def cancel_payment(ctx: OperationContext, data: CancelIn) -> dict:
    payment = find_payment(data.id, data.reference, lock=True)
    if payment.status in FINISHED:
        raise Conflict(str(NOT_CANCELLABLE), code="payment.not_cancellable")
    return _move(
        ctx,
        payment,
        Payment.Status.CANCELLED,
        events.PAYMENT_CANCELLED,
        cancel_reason=data.reason,
    )
