"""The roles of a business (``base.role.list``) and «What it allows» of one (``base.role.detail``, BASE-F82): app by app,
each permission with its phrase and what the role does with it.

A permission the role lacks is still done «with approval» when an app that is on names one of its commands as
approvable (``approvals``): a manager approves it on the spot with their PIN (BASE-F84).
"""

from collections import Counter
from collections.abc import Collection, Iterable
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
from base.approvals import approvable_permissions
from base.models import HubUser, Membership
from base.models.roles import BusinessRole
from base.permissions import (
    INVITATION_ALONE, RoleHeld, VIEW_HOME, grantable, permissions_of_business_role, permissions_of_role, role_held,
    states_of_business_role,
)
from base.roles import APPROVAL, basic_state, to_review
from base.schemas.roles import RoleDetailIn, RoleDetailOut, RoleListIn, RoleListOut
from base.sensitive import DATA_PERMISSIONS

from .people import people_of

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
    members, on, ruling = members_by_role(ctx.scope), configs_on(ctx.scope), ruling_key(ctx)
    own = sorted(BusinessRole.objects.all(), key=lambda role: role.name.casefold())
    with translation.override(ctx.language):
        rows = [
            *(
                {**_basic_out(role, members), "permissions": len(permissions_of_role(role.value))}
                for role in people_rules.ROLE_ORDER
            ),
            *(_own_row(role, members, on) for role in own),
        ]
    return {"roles": [{**row, "mine": row["key"] == ruling} for row in rows]}


@operation(
    "base.role.detail",
    kind="query",
    permission=VIEW_HOME,
    input=RoleDetailIn,
    output=RoleDetailOut,
    ai=AI(
        description=(
            "Reads what one role of this business (owner, admin, manager, employee, accountant or one of its own) "
            "allows, app by app: each permission in business words and whether the role does it, does it only with a "
            "manager's approval or not at all. A basic role is given on erplora.com and is not changed here; the "
            "business's own (origin own) are changed with base.role.update."
        ),
        asks={
            "en": ("what does the employee role allow?", "which permissions does the accountant role have?"),
            "es": ("¿qué permite el rol de empleado?", "¿qué permisos tiene el rol de gestoría?"),
        },
    ),
)
def role_detail(ctx: OperationContext, data: RoleDetailIn) -> dict:
    """Employees › Roles › What it allows: one role, read only; its panels from the ``offset``-th on."""
    with translation.override(ctx.language):
        basic = basic_role(data.role)
        on = configs_on(ctx.scope)
        members = members_by_role(ctx.scope)
        if basic is not None:
            panels = _panels(on, states_of(RoleHeld(basic.value, None), on))
            found = {**_basic_out(basic, members), "apps": panels[data.offset :]}
        else:
            role = business_role(data.role)
            review = to_review(role.states, grantable(on))
            panels = _panels(on, states_of(RoleHeld(role.origin, role), on), review)
            found = {**_own_out(role, members, on), "apps": panels[data.offset :]}
    return {**found, "mine": found["key"] == ruling_key(ctx)}


def states_of(held: RoleHeld, configs: list[LiveAppConfig]) -> dict[str, str]:
    """What the role that rules does today with each permission of ``configs``: a basic one, with all they declare; one of
    the business, with those it may hold."""
    approved = approvable_permissions(configs)
    if held.own is not None:
        return states_of_business_role(held.own, configs, approved)
    given = permissions_of_role(held.invitation)
    return {permission: basic_state(permission, given, approved) for config in configs for permission in config.permissions}


def signed_in_role_held(ctx: OperationContext) -> RoleHeld | None:
    """What who asks is in this business; ``None`` for nobody, the platform, an API key or somebody of another one."""
    return role_held(ctx.actor, ctx.scope)


def ruling_key(ctx: OperationContext) -> str | None:
    """The key of the role that rules what who asks may do, as ``base.role.list`` names it; ``None`` without one."""
    held = signed_in_role_held(ctx)
    if held is None:
        return None
    return str(held.own.pk) if held.own is not None else held.invitation


def role_label(held: RoleHeld) -> str:
    """How the role that rules is named: as the business wrote it, or the membership's one in the active language
    (a basic role, or ERPlora's support)."""
    if held.own is not None:
        return held.own.name
    return str(dict(Membership._meta.get_field("role").flatchoices)[held.invitation])


def approvable_of(ctx: OperationContext, held: RoleHeld) -> list[str]:
    """What who asks may do only if a manager approves it with their PIN, of the apps that are on."""
    states = states_of(held, configs_on(ctx.scope))
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


def members_by_role(scope: Scope) -> Counter[str]:
    """How many people of the business have each role, by its key. Whoever holds a role of the business counts in it and
    not in the role of their invitation, save the owner and the accountancy firm, whom it never rules
    (``base.permissions.INVITATION_ALONE``)."""
    invited = {person["id"]: person["role"] for person in people_of(scope.key)}
    ruled = [username for username, role in invited.items() if role not in INVITATION_ALONE]
    holders = HubUser.objects.filter(username__in=ruled, business_role__isnull=False)
    own = {username: str(role) for username, role in holders.values_list("username", "business_role_id")}
    return Counter((invited | own).values())


def role_row(ctx: OperationContext, role: BusinessRole) -> dict[str, Any]:
    """A role of the business as the list shows it."""
    row = _own_row(role, members_by_role(ctx.scope), configs_on(ctx.scope))
    return {**row, "mine": row["key"] == ruling_key(ctx)}


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


def _panels(on: list[LiveAppConfig], states: dict[str, str], review: Collection[str] = ()) -> list[dict[str, Any]]:
    """«What it allows», a panel per app: the business first, each module by its name, the sensitive data last; each
    permission ``states`` says, with its phrase, whether a manager can approve it and whether it is left to ``review``."""
    approvable = approvable_permissions(on)

    def lines(permissions: Iterable[tuple[str, object]]) -> list[dict]:
        return [
            {
                "permission": permission,
                "phrase": str(phrase),
                "state": states[permission],
                "approvable": permission in approvable,
                "to_review": permission in review,
            }
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
