"""The roles of the business: add one, change it or retire it (STAFF-F04)."""

from typing import Any

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.staff import events
from apps.staff.models import Role
from apps.staff.queries.roles import ROLE_NOT_FOUND, load_role
from apps.staff.schemas.roles import RoleIn, RoleOut, RolePatchIn

ROLE_NAME_TAKEN = _("A role with that name already exists.")

ROLE_UNIQUE = "staff_role_name_unique"


@operation(
    "staff.role.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=RoleIn,
    output=RoleOut,
    ai={
        "asks": {
            "en": (
                "create a Receptionist role",
                "add the role Senior stylist in blue",
                "new staff role for the kitchen helpers",
            ),
            "es": (
                "crea el rol Recepcionista",
                "añade el rol Estilista sénior en azul",
                "rol nuevo del personal para los ayudantes de cocina",
            ),
        },
        "description": "Creates a role of the business (a catalogue label such as stylist; it grants no "
        "permission).",
        "risk": "normal",
    },
)
def create_role(ctx: OperationContext, data: RoleIn) -> Role | None:
    role = Role(**data.model_dump())
    _save_role(role)
    record_event(ctx, events.ROLE_CREATED, {"id": str(role.id)})
    return load_role(role.id)


@operation(
    "staff.role.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="staff.manage_settings",
    input=RolePatchIn,
    output=RoleOut,
    ai={
        "asks": {
            "en": (
                "change the name of the Waiter role to Floor staff",
                "edit the Stylist role so it goes first in the list",
                "retire the Trainee role so it is no longer offered",
            ),
            "es": (
                "cambia el nombre del rol Camarero a Sala",
                "edita el rol de Estilista para que vaya el primero",
                "retira el rol de Becario para que no se ofrezca más",
            ),
        },
        "description": "Changes a role (name, description, colour, order) or retires it (is_active false) "
        "so it is no longer offered.",
        "risk": "normal",
    },
)
def update_role(ctx: OperationContext, data: RolePatchIn) -> Role | None:
    role = Role.objects.select_for_update().filter(pk=data.id).first()
    if role is None:
        raise NotFound(str(ROLE_NOT_FOUND))
    sent = data.model_dump(exclude_unset=True, exclude_none=True, exclude={"id"})
    changes = {
        field: value for field, value in sent.items() if getattr(role, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(role, field, value)
        _save_role(role, update_fields=[*changes, "updated_at"])
        record_event(ctx, events.ROLE_UPDATED, {"id": str(role.id)})
    return load_role(role.id)


def _save_role(role: Role, **options: Any) -> None:
    try:
        with atomic():
            role.save(**options)
    except IntegrityError as error:
        if ROLE_UNIQUE not in str(error):
            raise
        raise Conflict(str(ROLE_NAME_TAKEN), code="staff.role_name_taken") from None
