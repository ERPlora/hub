"""Writes of the payment methods: create, edit, deactivate and activate. A name is unique whatever the case, also
when two saves take it at once."""

from django.db import IntegrityError
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.payment import events
from apps.payment.models import PaymentMethod
from apps.payment.queries import find_method, method_row
from apps.payment.schemas import MethodIn, MethodOut, MethodPatchIn, MethodRefIn
from apps.payment.services.actor import _actor

METHOD_NAME_TAKEN = _(
    "There is already a payment method with that name. Pick another name."
)
METHOD_ALREADY_INACTIVE = _("That payment method is already deactivated.")
METHOD_ALREADY_ACTIVE = _("That payment method is already active.")


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=MethodIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add the Santander bank account to pay suppliers from",
                "set up a new bank account for outgoing payments",
            ),
            "es": (
                "da de alta la cuenta bancaria del Santander para pagar a proveedores",
                "añade la tarjeta de empresa para los pagos salientes",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=MethodPatchIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "rename the Sabadell bank account to Main bank",
                "change the number of the Santander bank account",
            ),
            "es": (
                "cambia el nombre de la cuenta del banco Sabadell a Banco principal",
                "cambia el número de la cuenta bancaria del Santander",
            ),
        },
        "description": "Change a payment method (named by its id or its name): only the fields sent change. "
        "The payments that used it keep it.",
        "risk": "normal",
        "check": "payment.method.get",
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=MethodRefIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "stop using the Sabadell bank account for new payments",
                "the old Santander bank account must not take outgoing payments any more",
            ),
            "es": (
                "que la cuenta del Sabadell ya no se use en pagos nuevos",
                "la tarjeta de empresa antigua ya no vale para los pagos salientes",
            ),
        },
        "description": "Deactivate a payment method (named by its id or its name): a new payment can no "
        "longer use it; the payments that used it keep it. It is never deleted.",
        "risk": "normal",
        "check": "payment.method.get",
    },
)
def deactivate_method(ctx: OperationContext, data: MethodRefIn) -> dict:
    return _set_active(ctx, data, False)


@operation(
    "payment.method.activate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="payment.add_payment",
    input=MethodRefIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "let the Sabadell bank account be used for payments again",
                "reactivate the Santander bank account for outgoing payments",
            ),
            "es": (
                "reactiva la cuenta bancaria del Sabadell para los pagos",
                "que la tarjeta de empresa vuelva a servir para pagar a proveedores",
            ),
        },
        "description": "Activate a deactivated payment method again (named by its id or its name), so new "
        "payments can use it.",
        "risk": "normal",
        "check": "payment.method.get",
    },
)
def activate_method(ctx: OperationContext, data: MethodRefIn) -> dict:
    return _set_active(ctx, data, True)
