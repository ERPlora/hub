"""The drawers: finding one by its id or its name, and their reads."""

from uuid import UUID

from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.cash_register.models import Register
from apps.cash_register.schemas import (
    RegisterGetIn,
    RegisterListIn,
    RegisterOut,
    RegisterPage,
)

REGISTER_NOT_FOUND = _("That drawer is not available.")


def register_row(register: Register) -> dict:
    return {"id": register.id, "name": register.name, "is_active": register.is_active}


def find_register(
    register_id: UUID | None,
    name: str | None,
    *,
    lock: bool = False,
    active: bool = False,
) -> Register:
    registers = Register.objects.select_for_update() if lock else Register.objects.all()
    if active:
        registers = registers.filter(is_active=True)
    register = (
        registers.filter(pk=register_id).first()
        if register_id is not None
        else registers.annotate(lowered=Lower("name"))
        .filter(lowered=(name or "").strip().lower())
        .first()
    )
    if register is None:
        raise NotFound(str(REGISTER_NOT_FOUND), code="cash_register.register_not_found")
    return register


@operation(
    "cash_register.register.list",
    kind="query",
    permission="cash_register.view_session",
    input=RegisterListIn,
    output=RegisterPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which drawers do we have?",
                "list the active drawers",
            ),
            "es": (
                "¿qué cajones tenemos?",
                "lista los cajones activos",
            ),
        },
        "description": "List the drawers by name: search by name, only active or inactive ones."
    },
)
def list_registers(ctx: OperationContext, params: RegisterListIn) -> dict:
    registers = Register.objects.all()
    if params.search:
        registers = registers.filter(name__icontains=params.search.strip())
    if params.is_active is not None:
        registers = registers.filter(is_active=params.is_active)
    registers = registers.order_by(Lower("name"), "id")
    page = registers[params.offset : params.offset + params.limit]
    return {
        "rows": [register_row(register) for register in page],
        "total": registers.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "cash_register.register.get",
    kind="query",
    permission="cash_register.view_session",
    input=RegisterGetIn,
    output=RegisterOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the Terrace drawer active?",
                "show me the details of the bar drawer",
            ),
            "es": (
                "¿está activo el cajón Terraza?",
                "dame los datos del cajón de la barra",
            ),
        },
        "description": "One drawer by its id: its name and whether it is active.",
    },
)
def get_register(ctx: OperationContext, params: RegisterGetIn) -> dict:
    return register_row(find_register(params.register_id, None))
