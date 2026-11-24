"""The roles of a business (``base.role.list``) and «What it allows» of one (``base.role.detail``, BASE-F82): app by app,
each permission with its phrase and what the role does with it.

A permission the role lacks is still done «with approval» when an app that is on names one of its commands as
approvable (``approvals``): a manager approves it on the spot with their PIN (BASE-F84).
"""

from collections import Counter
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import AI, operation

from base import people as people_rules
from base.apps_on import active_apps
from base.approvals import approvable
from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import RoleHeld, VIEW_HOME, grantable, permissions_of_business_role, permissions_of_role, role_held
from base.roles import APPROVAL, basic_state, effective, to_review
from base.schemas.roles import RoleDetailOut, RoleIn, RoleListIn, RoleListOut
from base.sensitive import DATA_PERMISSIONS

from .people import is_a_person, people_of

BUSINESS = _("The business")
SENSITIVE_DATA = _("Sensitive data")
ROLE_NOT_FOUND = _("This role does not exist in this business.")


@operation(
    "base.role.list",
    kind="query",
    permission=VIEW_HOME,
    input=RoleListIn,
    output=RoleListOut,
    ai=AI(
        description=(
            "Lists the roles of this business: the basic ones of erplora.com (owner, admin, manager, employee, "
            "accountant) and the ones the business made (origin own), each with how many people have it, how many "
            "permissions of the apps it gives and whether it has new permissions to review. A basic role is given on "
            "erplora.com."
        ),
        asks={
            "en": ("how many managers do we have?", "what can a manager do here?"),
            "es": ("¿qué roles hay en el negocio?", "¿cuántos encargados tenemos?"),
        },
    ),
)
def role_list(ctx: OperationContext, data: RoleListIn) -> dict:
    """Employees › Roles: erplora.com's, from the top, and the business's own by their name."""
    members, on = members_by_role(ctx.scope), configs_on(ctx.scope)
    own = sorted(BusinessRole.objects.all(), key=lambda role: role.name.casefold())
    with translation.override(ctx.language):
        return {
            "roles": [
                *(
                    {**_basic_out(role, members), "permissions": len(permissions_of_role(role.value))}
                    for role in people_rules.ROLE_ORDER
                ),
                *(_own_row(role, members, on) for role in own),
            ]
        }


@operation(
    "base.role.detail",
    kind="query",
    permission=VIEW_HOME,
    input=RoleIn,
    output=RoleDetailOut,
    ai=AI(
        description=(
            "Reads what one role of this business allows, app by app: each permission in business words and whether "
            "the role does it, does it only with a manager's approval or not at all. A basic role is given on "
            "erplora.com and is not changed here; the business's own (origin own) are changed with base.role.update."
        ),
        asks={
            "en": ("what does the employee role allow?", "which permissions does the accountant role have?"),
            "es": ("¿qué permite el rol de empleado?", "¿qué permisos tiene el rol de gestoría?"),
        },
    ),
)
def role_detail(ctx: OperationContext, data: RoleIn) -> dict:
    """Employees › Roles › What it allows: one role, read only."""
    with translation.override(ctx.language):
        basic = basic_role(data.role)
        on = configs_on(ctx.scope)
        members = members_by_role(ctx.scope)
        if basic is not None:
            return {**_basic_out(basic, members), "apps": _panels(on, _states_of_basic(basic.value, on))}
        role = business_role(data.role)
        return {**_own_out(role, members, on), "apps": _panels(on, _states_of_own(role, on))}


def _states_of_basic(role: str, on: list[LiveAppConfig]) -> dict[str, str]:
    """What a basic role does today with each permission of the apps ``on``."""
    given, approved = permissions_of_role(role), approvable_permissions(on)
    return {permission: basic_state(permission, given, approved) for config in on for permission in config.permissions}


def _states_of_own(role: BusinessRole, on: list[LiveAppConfig]) -> dict[str, str]:
    """What a role of the business does today with each permission of the apps ``on`` it may hold."""
    given = permissions_of_role(role.origin)
    return effective(role.states, grantable(on), given=given, approvable=approvable_permissions(on))


def signed_in_role_held(ctx: OperationContext) -> RoleHeld | None:
    """What who asks is in this business; ``None`` for nobody, the platform, an API key or somebody of another one."""
    return role_held(ctx.actor, ctx.scope) if is_a_person(ctx.actor) else None


def role_label(held: RoleHeld) -> str:
    """How the role that rules is named: as the business wrote it, or the basic one in the active language."""
    return str(Membership.Role(held.invitation).label) if held.own is None else held.own.name


def approvable_of(ctx: OperationContext, held: RoleHeld) -> list[str]:
    """What who asks may do only if a manager approves it with their PIN, of the apps that are on."""
    on = configs_on(ctx.scope)
    states = _states_of_basic(held.invitation, on) if held.own is None else _states_of_own(held.own, on)
    return sorted(permission for permission, state in states.items() if state == APPROVAL)


def roles_to_review(scope: Scope) -> int:
    """How many roles of the business have something to review: an app turned on, or a permission added, after they were
    saved."""
    apps = grantable(configs_on(scope))
    return sum(1 for states in BusinessRole.objects.values_list("states", flat=True) if to_review(states, apps))


def basic_role(key: str) -> Membership.Role | None:
    """The basic role ``key`` names, as erplora.com does; ``None`` for anything else."""
    return next((role for role in people_rules.ROLE_ORDER if role.value == key), None)


def business_role(key: str, *, for_update: bool = False) -> BusinessRole:
    """The role this business made whose id ``key`` is; ``NotFound`` for anything else."""
    try:
        roles = BusinessRole.objects.select_for_update() if for_update else BusinessRole.objects
        return roles.get(pk=UUID(key))
    except (ValueError, BusinessRole.DoesNotExist):
        raise NotFound(str(ROLE_NOT_FOUND), code="base.role_not_found") from None


def configs_on(scope: Scope) -> list[LiveAppConfig]:
    """The apps that are on in ``scope`` and declare permissions, base among them."""
    active = active_apps(scope)
    return [config for config in all_live_app_configs() if config.permissions and config.label in active]


def approvable_permissions(configs: Iterable[LiveAppConfig]) -> frozenset[str]:
    """The permissions a manager's approval stands in for: those of the commands ``configs`` name approvable."""
    return frozenset(
        found[0].permission
        for config in configs
        for name in getattr(config, "approvals", {})
        if (found := approvable(name)) is not None
    )


def members_by_role(scope: Scope) -> Counter[str]:
    """How many people of the business have each role, by its key. Whoever holds a role of the business counts in it and
    not in the role of their invitation, save the owner, whom it never rules (``base.permissions.access_for``)."""
    invited = {person["id"]: person["role"] for person in people_of(scope.key)}
    ruled = [username for username, role in invited.items() if role != Membership.Role.OWNER]
    holders = HubUser.objects.filter(username__in=ruled, business_role__isnull=False)
    own = {username: str(role) for username, role in holders.values_list("username", "business_role_id")}
    return Counter((invited | own).values())


def role_row(scope: Scope, role: BusinessRole) -> dict[str, Any]:
    """A role of the business as the list shows it."""
    return _own_row(role, members_by_role(scope), configs_on(scope))


def _own_row(role: BusinessRole, members: Counter[str], on: list[LiveAppConfig]) -> dict[str, Any]:
    return {**_own_out(role, members, on), "permissions": len(permissions_of_business_role(role))}


def _basic_out(role: Membership.Role, members: Counter[str]) -> dict[str, Any]:
    return {
        "key": role.value,
        "label": str(role.label),
        "description": "",
        "origin": "basic",
        "members": members[role.value],
        "to_review": False,
    }


def _own_out(role: BusinessRole, members: Counter[str], on: list[LiveAppConfig]) -> dict[str, Any]:
    return {
        "key": str(role.pk),
        "label": role.name,
        "description": role.description,
        "origin": "own",
        "members": members[str(role.pk)],
        "to_review": bool(to_review(role.states, grantable(on))),
    }


def _panels(on: list[LiveAppConfig], states: dict[str, str]) -> list[dict[str, Any]]:
    """«What it allows», a panel per app: the business first, each module by its name, the sensitive data last; each
    permission ``states`` says, with its phrase."""

    def lines(permissions: Iterable[tuple[str, object]]) -> list[dict]:
        return [
            {"permission": permission, "phrase": str(phrase), "state": states[permission]}
            for permission, phrase in permissions
            if permission in states
        ]

    base = next(config for config in on if config.label == "base")
    modules = sorted((config for config in on if config.label != "base"), key=lambda c: str(c.verbose_name).casefold())
    return [
        {"app": "base", "name": str(BUSINESS), "permissions": lines(_own(base, sensitive=False))},
        *({"app": c.label, "name": str(c.verbose_name), "permissions": lines(c.permissions.items())} for c in modules),
        {"app": "sensitive", "name": str(SENSITIVE_DATA), "permissions": lines(_own(base, sensitive=True))},
    ]


def _own(base: LiveAppConfig, *, sensitive: bool) -> list[tuple[str, object]]:
    """Base's permissions with their phrases: the business's own, or the data ones (``base.sensitive``)."""
    return [(permission, phrase) for permission, phrase in base.permissions.items() if (permission in DATA_PERMISSIONS) == sensitive]
