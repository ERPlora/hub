"""Write operations of the payment app: one operation = one transaction, with its events in the outbox.

Every check runs before the first write, so a refusal leaves no trace: no row, no reference number
spent, no event (the old module answered «ok» to a step from the wrong state, spent a number on a
payment it did not save and emitted the event anyway). A step locks the payment's row first, so two
people pressing at once go one after the other and the second hears why. The reference of the day
comes from the counter's row raised with ``UPDATE … RETURNING`` in the payment's transaction (never a
sequence). A method name two saves take at once ends in the database's unique constraint, translated
to the same 409 as the check. A payment sent with the key of its attempt is recorded once: the same
attempt sent again (a retry, a double tap, both at once) answers the payment already recorded, without
a second number or notice.
"""

from django.db import IntegrityError
from django.db.models import F
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.payment import events
from apps.payment.models import (
    ACTOR_MAX_LENGTH,
    Payment,
    PaymentCounter,
    PaymentMethod,
)
from apps.payment.queries import (
    find_method,
    find_payment,
    method_row,
    payment_row,
)
from apps.payment.schemas import (
    CancelIn,
    MethodIn,
    MethodOut,
    MethodPatchIn,
    MethodRefIn,
    PaymentIn,
    PaymentOut,
    PaymentRefIn,
)
from base import operations as platform

METHOD_NAME_TAKEN = _(
    "There is already a payment method with that name. Pick another name."
)
METHOD_INACTIVE = _("That payment method is deactivated: pick an active one.")
METHOD_ALREADY_INACTIVE = _("That payment method is already deactivated.")
METHOD_ALREADY_ACTIVE = _("That payment method is already active.")
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


def _actor(ctx: OperationContext) -> str:
    """Who acted, as a person reads it: an account's full name, else its email, else its username;
    the platform or an API key as they name themselves."""
    actor = ctx.actor
    if actor is None:
        return ""
    if hasattr(actor, "get_username"):
        name = actor.get_full_name() or actor.email or actor.get_username()
    else:
        name = str(actor)
    return name[:ACTOR_MAX_LENGTH]


# ── Methods ───────────────────────────────────────────────────────────────────────────────────


def _name_taken() -> Conflict:
    return Conflict(
        str(METHOD_NAME_TAKEN),
        code="payment.method_exists",
        fields={"name": str(METHOD_NAME_TAKEN)},
    )


def _check_name(name: str, *, other_than=None) -> None:
    taken = PaymentMethod.objects.annotate(lower=Lower("name")).filter(
        lower=name.lower()
    )
    if other_than is not None:
        taken = taken.exclude(pk=other_than)
    if taken.exists():
        raise _name_taken()


def _save_method(method: PaymentMethod, **kwargs) -> None:
    """Saves ``method``; two saves of one name at once end in the unique constraint → the same 409."""
    try:
        with atomic():
            method.save(**kwargs)
    except IntegrityError:
        raise _name_taken() from None


@operation(
    "payment.method.create",
    kind="command",
    permission="payment.add_payment",
    input=MethodIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "description": "Create an account the business pays its outgoing payments from (a bank account, the "
        "company card, the cash drawer), with its unique name, its type and an optional account reference. "
        "Not a tender of the till: those are Sales' payment methods.",
        "risk": "normal",
    },
)
def create_method(ctx: OperationContext, data: MethodIn) -> dict:
    _check_name(data.name)
    actor = _actor(ctx)
    method = PaymentMethod(
        name=data.name,
        method_type=data.method_type,
        bank_account_ref=data.bank_account_ref,
        created_by=actor,
        updated_by=actor,
    )
    _save_method(method)
    record_event(
        ctx, events.METHOD_CREATED, {"id": str(method.id), "name": method.name}
    )
    return method_row(method)


@operation(
    "payment.method.update",
    kind="command",
    permission="payment.add_payment",
    input=MethodPatchIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "description": "Change a payment method (named by its id or its name): only the fields sent change. "
        "The payments that used it keep it.",
        "risk": "normal",
    },
)
def update_method(ctx: OperationContext, data: MethodPatchIn) -> dict:
    method = find_method(data.id, data.method, lock=True)
    values = {
        field: getattr(data, field)
        for field in ("name", "method_type", "bank_account_ref")
        if field in data.model_fields_set and getattr(data, field) is not None
    }
    changed = [
        field for field, value in values.items() if getattr(method, field) != value
    ]
    if "name" in changed:
        _check_name(values["name"], other_than=method.pk)
    if changed:
        for field in changed:
            setattr(method, field, values[field])
        method.updated_by = _actor(ctx)
        _save_method(method, update_fields=[*changed, "updated_by", "updated_at"])
        record_event(
            ctx,
            events.METHOD_UPDATED,
            {"id": str(method.id), "name": method.name, "changed": changed},
        )
    return method_row(method)


def _set_active(ctx: OperationContext, data: MethodRefIn, active: bool) -> dict:
    method = find_method(data.id, data.method, lock=True)
    if method.is_active == active:
        message, code = (
            (METHOD_ALREADY_ACTIVE, "payment.method_already_active")
            if active
            else (METHOD_ALREADY_INACTIVE, "payment.method_already_inactive")
        )
        raise Conflict(str(message), code=code)
    method.is_active = active
    method.updated_by = _actor(ctx)
    method.save(update_fields=["is_active", "updated_by", "updated_at"])
    record_event(
        ctx,
        events.METHOD_ACTIVATED if active else events.METHOD_DEACTIVATED,
        {"id": str(method.id), "name": method.name},
    )
    return method_row(method)


@operation(
    "payment.method.deactivate",
    kind="command",
    permission="payment.add_payment",
    input=MethodRefIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "description": "Deactivate a payment method (named by its id or its name): a new payment can no "
        "longer use it; the payments that used it keep it. It is never deleted.",
        "risk": "normal",
    },
)
def deactivate_method(ctx: OperationContext, data: MethodRefIn) -> dict:
    return _set_active(ctx, data, False)


@operation(
    "payment.method.activate",
    kind="command",
    permission="payment.add_payment",
    input=MethodRefIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "description": "Activate a deactivated payment method again (named by its id or its name), so new "
        "payments can use it.",
        "risk": "normal",
    },
)
def activate_method(ctx: OperationContext, data: MethodRefIn) -> dict:
    return _set_active(ctx, data, True)


# ── Payments ──────────────────────────────────────────────────────────────────────────────────


def _method_to_pay_from(data: PaymentIn) -> PaymentMethod:
    """The active method the payment leaves from; a missing or deactivated one is refused under the
    field the caller used (the screen sends ``method_id``, the assistant may say ``method``)."""
    field = "method_id" if data.method_id is not None else "method"
    try:
        method = find_method(data.method_id, data.method, lock=True)
    except NotFound as missing:
        raise InvalidPayload(
            missing.message, code=missing.code, fields={field: missing.message}
        ) from None
    if not method.is_active:
        raise InvalidPayload(
            str(METHOD_INACTIVE),
            code="payment.method_inactive",
            fields={field: str(METHOD_INACTIVE)},
        )
    return method


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
        "description": "Record an outgoing payment (to a supplier, a transfer, a refund that is not a sale's) "
        "as a draft, with its reference of the day: the active method it leaves from (by id or name), the "
        "day, the amount in minor units (12,50 € = 1250), the beneficiary and optionally the concept, IBAN, "
        "supplier's invoice and currency. It moves no money. Never use it to charge a customer.",
        "risk": "normal",
    },
)
def create_payment(ctx: OperationContext, data: PaymentIn) -> dict:
    # Without one, the business's currency: its country's (BASE-F50), never a euro fixed here (payments#35, #38).
    currency = data.currency or platform.business_currency(ctx.scope)
    recorded = _recorded(data, currency)
    if recorded is not None:
        return recorded
    method = _method_to_pay_from(data)
    day = timezone.localdate()
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


def _step(
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
    permission="payment.approve_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
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
    permission="payment.add_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
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
    permission="payment.add_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
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
    permission="payment.approve_payment",
    input=CancelIn,
    output=PaymentOut,
    expose_api=True,
    ai={
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
