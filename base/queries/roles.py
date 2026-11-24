"""«What it allows» of a basic role (BASE-F82): app by app, each permission with its phrase and what the role does with it.

A permission the role lacks is still done «with approval» when an app that is on names one of its commands as
approvable (``approvals``): a manager approves it on the spot with their PIN (BASE-F84).
"""

from collections.abc import Iterable

from django.utils import translation
from django.utils.translation import gettext, gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.meta import LiveAppConfig, all_live_app_configs
from live.operations import AI, operation

from base import people as people_rules
from base.apps_on import active_apps
from base.approvals import approvable
from base.models import Membership
from base.permissions import VIEW_HOME, permissions_of_role
from base.roles import basic_state
from base.schemas.roles import RoleDetailIn, RoleDetailOut
from base.sensitive import DATA_PERMISSIONS

from .people import people_of

BUSINESS = _("The business")
SENSITIVE_DATA = _("Sensitive data")


@operation(
    "base.role.detail",
    kind="query",
    permission=VIEW_HOME,
    input=RoleDetailIn,
    output=RoleDetailOut,
    ai=AI(
        description=(
            "Reads what one basic role of this business allows, app by app: each permission in business words and "
            "whether the role does it, does it only with a manager's approval or not at all. Roles are given on "
            "erplora.com and are not changed here."
        ),
        asks={
            "en": ("what does the employee role allow?", "which permissions does the accountant role have?"),
            "es": ("¿qué permite el rol de empleado?", "¿qué permisos tiene el rol de gestoría?"),
        },
    ),
)
def role_detail(ctx: OperationContext, data: RoleDetailIn) -> dict:
    """Employees › Roles › What it allows: one basic role, read only."""
    with translation.override(ctx.language):
        role = _basic_role(data.role)
        active = active_apps(ctx.scope)
        on = [config for config in all_live_app_configs() if config.permissions and config.label in active]
        given = permissions_of_role(role.value)
        approved = _approvable(on)

        def lines(permissions: Iterable[tuple[str, object]]) -> list[dict]:
            return [
                {"permission": permission, "phrase": str(phrase), "state": basic_state(permission, given, approved)}
                for permission, phrase in permissions
            ]

        base = next(config for config in on if config.label == "base")
        modules = sorted((config for config in on if config.label != "base"), key=lambda c: str(c.verbose_name).casefold())
        return {
            "key": role.value,
            "label": str(role.label),
            "origin": "basic",
            "members": sum(1 for person in people_of(ctx.scope.key) if person["role"] == role),
            "apps": [
                {"app": "base", "name": str(BUSINESS), "permissions": lines(_own(base, sensitive=False))},
                *({"app": c.label, "name": str(c.verbose_name), "permissions": lines(c.permissions.items())} for c in modules),
                {"app": "sensitive", "name": str(SENSITIVE_DATA), "permissions": lines(_own(base, sensitive=True))},
            ],
        }


def _basic_role(key: str) -> Membership.Role:
    for role in people_rules.ROLE_ORDER:
        if role.value == key:
            return role
    raise NotFound(gettext("This role does not exist in this business."), code="base.role_not_found")


def _own(base: LiveAppConfig, *, sensitive: bool) -> list[tuple[str, object]]:
    """Base's permissions with their phrases: the business's own, or the data ones (``base.sensitive``)."""
    return [(permission, phrase) for permission, phrase in base.permissions.items() if (permission in DATA_PERMISSIONS) == sensitive]


def _approvable(configs: Iterable[LiveAppConfig]) -> frozenset[str]:
    """The permissions a manager's approval stands in for: those of the commands the apps that are on name approvable."""
    return frozenset(
        found[0].permission
        for config in configs
        for name in getattr(config, "approvals", {})
        if (found := approvable(name)) is not None
    )
