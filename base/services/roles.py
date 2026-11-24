"""The roles a business makes for itself (``base.role.create``, ``update`` and ``delete``, BASE-F127 to BASE-F129)."""

from functools import partial

from django.db import IntegrityError
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, PermissionDenied
from live.operations import AI, atomic, on_commit, operation
from live.outbox import record_event

from base import events, queries, roles
from base.models import HubUser
from base.models.roles import NAME_UNIQUE, BusinessRole
from base.permissions import MANAGE_ROLES, OWNER_ONLY, grantable, permissions_of_business_role, permissions_of_role
from base.schemas.roles import RoleCreateIn, RoleDeleteOut, RoleIn, RoleRowOut, RoleUpdateIn
from base.services.sessions import _wake_open_apps

STATE_LABELS = {
    roles.ON: _("Allowed"),
    roles.APPROVAL: _("With approval"),
    roles.OFF: _("No"),
}


@operation(
    "base.role.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_ROLES,
    input=RoleCreateIn,
    output=RoleRowOut,
    ai=AI(
        description=(
            "Makes a role of this business by duplicating another, basic or the business's own: it allows the same "
            "until base.role.update changes it. Give it the name the person says. It never allows more than who makes "
            "it may do."
        ),
        asks={
            "en": (
                "create a Cashier role from the employee one",
                "duplicate the manager role and call it Shift lead",
                "make a new role for the kitchen copied from the employee one",
            ),
            "es": (
                "crea el rol Cajero a partir del de empleado",
                "duplica el rol de encargado y llámalo Jefe de turno",
                "hazme un rol nuevo para cocina copiado del de empleado",
            ),
        },
    ),
)
def role_create(ctx: OperationContext, data: RoleCreateIn) -> dict:
    """«Duplicate»: the states the other role shows for a basic one, the saved ones for one of the business's own (what
    it was not saved with stays to review in the copy too)."""
    basic = queries.roles.basic_role(data.based_on)
    if basic is None:
        source = queries.roles.business_role(data.based_on)
        origin, states = source.origin, dict(source.states)
    else:
        origin, states = basic.value, _states_of_basic(ctx, basic.value)
    role = BusinessRole(name=_named(data.name), description=data.description.strip(), origin=origin, states=states)
    _held_by_who_asks(ctx, permissions_of_business_role(role))
    _save(role)
    record_event(ctx, events.ROLE_CREATED, {"id": str(role.pk)})
    return queries.roles.role_row(ctx.scope, role)


def _states_of_basic(ctx: OperationContext, origin: str) -> dict[str, str]:
    on = queries.roles.configs_on(ctx.scope)
    approved = queries.roles.approvable_permissions(on)
    return roles.effective({}, grantable(on), given=permissions_of_role(origin), approvable=approved)


def _update_summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """Each permission in its business words, as «What it allows» says it, and what it becomes."""
    phrases = {
        permission: str(phrase)
        for config in queries.roles.configs_on(ctx.scope)
        for permission, phrase in config.permissions.items()
    }
    changes = arguments.get("states")
    if not isinstance(changes, dict) or not changes:
        return fields
    lines = [
        {"name": permission, "label": phrases[permission], "kind": "text", "value": str(STATE_LABELS[state])}
        for permission, state in changes.items()
        if permission in phrases and state in STATE_LABELS
    ]
    return [*(field for field in fields if field["name"] != "states"), *lines]


@operation(
    "base.role.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_ROLES,
    input=RoleUpdateIn,
    output=RoleRowOut,
    ai={
        "description": (
            "Changes a role the business made (never a basic one: duplicate it with base.role.create): its name, its "
            "description or what it allows. Send only the permissions that change, by their name in base.role.detail. "
            "It never allows more than who changes it may do. Whoever has the role notices at once."
        ),
        "risk": "high",
        "preview": {"operation": "base.role.detail", "fields": ["members"]},
        "summary": _update_summary,
        "asks": {
            "en": (
                "the Cashier role shouldn't be able to void sales",
                "let the Shift lead role see the costs",
                "rename the Cashier role to Evening till",
            ),
            "es": (
                "que el rol Cajero no pueda anular ventas",
                "deja que el rol Jefe de turno vea los costes",
                "cambia el nombre del rol Cajero a Caja de tarde",
            ),
        },
    },
)
def role_update(ctx: OperationContext, data: RoleUpdateIn) -> dict:
    """«Save»: what is sent changes and nothing else; every open device of the business reads it again."""
    sent = data.model_dump(exclude_none=True, exclude={"role"})
    if not sent:
        raise InvalidPayload(gettext("Nothing to change."), code="base.nothing_to_change")
    role = _own_role(data.role)
    if data.name is not None:
        role.name = _named(data.name)
    if data.description is not None:
        role.description = data.description.strip()
    if data.states:
        before = permissions_of_business_role(role)
        role.states = _changed_states(ctx, role, data.states)
        _held_by_who_asks(ctx, permissions_of_business_role(role) - before)
    _save(role)
    record_event(ctx, events.ROLE_UPDATED, {"id": str(role.pk)})
    on_commit(partial(_wake_open_apps, ctx.scope.key))
    return queries.roles.role_row(ctx.scope, role)


def _changed_states(ctx: OperationContext, role: BusinessRole, changes: dict[str, str]) -> dict[str, str]:
    """What ``role`` keeps once ``changes`` are saved in it: permissions of the apps that are on, none of them the
    owner's alone, and left to approval only what a manager can approve."""
    if OWNER_ONLY & changes.keys():
        message = gettext("That is only the owner's of the business: no role gives it.")
        raise PermissionDenied(message, code="base.role_owner_only", fields={"states": message})
    on = queries.roles.configs_on(ctx.scope)
    apps, approved = grantable(on), queries.roles.approvable_permissions(on)
    if not changes.keys() <= {permission for permissions in apps.values() for permission in permissions}:
        message = gettext("That permission is not of any app that is on in this business.")
        raise InvalidPayload(message, code="base.role_permission_unknown", fields={"states": message})
    if any(state == roles.APPROVAL and permission not in approved for permission, state in changes.items()):
        message = gettext("That cannot be approved with a PIN: choose allowed or no.")
        raise InvalidPayload(message, code="base.role_not_approvable", fields={"states": message})
    return roles.saved(role.states, apps, permissions_of_role(role.origin), approved, changes)


@operation(
    "base.role.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_ROLES,
    input=RoleIn,
    output=RoleDeleteOut,
    ai=AI(
        description=(
            "Deletes a role the business made, for good; never a basic one. Refused while somebody of the business has "
            "it."
        ),
        risk="high",
        preview={"operation": "base.role.detail", "fields": ["members"]},
        asks={
            "en": ("delete the Cashier role", "we don't use the Shift lead role any more, remove it"),
            "es": ("borra el rol Cajero", "ya no usamos el rol Jefe de turno, elimínalo"),
        },
    ),
)
def role_delete(ctx: OperationContext, data: RoleIn) -> dict:
    """«Delete»: while nobody of the business holds it; whoever left with it, or it never ruled, keeps none."""
    role = _own_role(data.role)
    key = str(role.pk)
    members = queries.roles.members_by_role(ctx.scope)[key]
    if members:
        raise Conflict(
            ngettext(
                "%(n)s person has this role. Give them another before deleting it.",
                "%(n)s people have this role. Give them another before deleting it.",
                members,
            )
            % {"n": members},
            code="base.role_in_use",
        )
    HubUser.objects.filter(business_role=role).update(business_role=None)
    role.delete()
    record_event(ctx, events.ROLE_DELETED, {"id": key})
    return {"key": key}


def _own_role(key: str) -> BusinessRole:
    if queries.roles.basic_role(key) is not None:
        raise Conflict(
            gettext("This is one of erplora.com's roles. Duplicate it and change the copy."), code="base.role_basic"
        )
    return queries.roles.business_role(key, for_update=True)


def _named(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        message = gettext("Give the role a name.")
        raise InvalidPayload(message, code="base.role_name_required", fields={"name": message})
    return name


def _held_by_who_asks(ctx: OperationContext, given: frozenset[str]) -> None:
    """Nobody gives a role what they may not do themselves."""
    if any(not ctx.has(permission) for permission in given):
        message = gettext("A role may not allow more than you may do yourself.")
        raise PermissionDenied(message, code="base.role_beyond_editor", fields={"states": message})


def _save(role: BusinessRole) -> None:
    try:
        with atomic():
            role.save()
    except IntegrityError as error:
        if NAME_UNIQUE not in str(error):
            raise
        message = gettext("There is already a role with that name. Choose another.")
        raise Conflict(message, code="base.role_name_taken", fields={"name": message}) from None
