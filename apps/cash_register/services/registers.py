"""The drawers (CASH_REGISTER-F02): created and renamed with a name no other drawer has, never deleted."""

from django.db import IntegrityError
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import Register
from apps.cash_register.queries.people import actor
from apps.cash_register.queries.registers import find_register, register_row
from apps.cash_register.schemas import RegisterIn, RegisterOut, RegisterUpdateIn

REGISTER_EXISTS = _("There is already a drawer with that name.")


def _name_taken(name: str, *, but: Register | None = None) -> bool:
    others = Register.objects.annotate(lowered=Lower("name")).filter(
        lowered=name.lower()
    )
    if but is not None:
        others = others.exclude(pk=but.pk)
    return others.exists()


def _refuse_taken_name() -> Conflict:
    return Conflict(
        str(REGISTER_EXISTS),
        code="cash_register.register_exists",
        fields={"name": str(REGISTER_EXISTS)},
    )


@operation(
    "cash_register.register.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.manage_settings",
    input=RegisterIn,
    output=RegisterOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add a drawer for the terrace",
                "create another till drawer for the bar",
            ),
            "es": (
                "añade el cajón de la terraza",
                "da de alta otro cajón para la barra",
            ),
        },
        "description": "Create a drawer by its name (Bar, Terrace), one per physical drawer; it is offered when opening a "
        "session. Two drawers never share a name.",
        "risk": "normal",
    },
)
def create_register(ctx: OperationContext, data: RegisterIn) -> dict:
    if _name_taken(data.name):
        raise _refuse_taken_name()
    try:
        with atomic():
            register = Register.objects.create(name=data.name, created_by=actor(ctx))
    except IntegrityError:
        raise _refuse_taken_name() from None
    record_event(ctx, events.REGISTER_CREATED, {"id": str(register.id)})
    return register_row(register)


@operation(
    "cash_register.register.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.manage_settings",
    input=RegisterUpdateIn,
    output=RegisterOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "rename the Bar drawer to Front",
                "set the terrace drawer to inactive",
                "activate the bar drawer again",
            ),
            "es": (
                "cambia el nombre del cajón Barra a Entrada",
                "pon el cajón de la terraza como inactivo",
                "vuelve a poner activo el cajón de la barra",
            ),
        },
        "description": "Rename a drawer, or deactivate it (it is no longer offered when opening) and activate it again. "
        "Name it by its id or its current name. A drawer is never deleted.",
        "risk": "normal",
    },
)
def update_register(ctx: OperationContext, data: RegisterUpdateIn) -> dict:
    register = find_register(data.register_id, data.register_name, lock=True)
    if data.name is not None and _name_taken(data.name, but=register):
        raise _refuse_taken_name()
    if data.name is not None:
        register.name = data.name
    if data.is_active is not None:
        register.is_active = data.is_active
    try:
        with atomic():
            register.save(update_fields=["name", "is_active", "updated_at"])
    except IntegrityError:
        raise _refuse_taken_name() from None
    record_event(ctx, events.REGISTER_UPDATED, {"id": str(register.id)})
    return register_row(register)
