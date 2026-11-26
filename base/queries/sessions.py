"""The SPA's own session (``base.session.me``): the user, its permissions, and the menu and apps it may see."""

import hashlib
from typing import Any

from django.utils import translation
from live.context import OperationContext
from live.operations import INTERNAL, operation

from base import activation, entitlement, home
from base.models import Hub, HubUser
from base.permissions import VIEW_HOME
from base.schemas.sessions import SessionAccessIn, SessionAccessOut, SessionMeIn, SessionMeOut

from .apps import _can_see, _may_use, open_entries
from .people import hub_user_of, person_label, staff_names
from .roles import approvable_of, role_label, signed_in_role_held


# Not an assistant tool: the SPA's own session, read at start.
@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut, ai=INTERNAL)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    The menu lists the entries of each module the person may open (``Nav.permission``), and only the modules with one;
    ``apps`` lists every module the person holds a permission of, since other screens read from it whether a module
    is on (the till sells the modifiers and menus a cashier never opens). ``locked`` names, per module, the entries
    the person may not open: the shell's gate answers them with «No access». Menu and apps list modules only
    (``home.shown_modules.shown_modules``: the reference app only in development, the tests or a demo's hub): a platform app such
    as ``base`` is always on and never shows. A module its business has no right to (``base.entitlement``) or turned
    off (``base.activation``) is ``off`` and has no menu: the shell's gate tells why its screens do not open. ``demo``
    says when the demo ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing
    else, which tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
    # Not on: a paid module without its right, or one the business turned off (base.activation); one whose tables the
    # hub's own database is still getting is «activating».
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    creating = activation.creating_apps(ctx.scope) if blocked else frozenset()
    with translation.override(ctx.language):
        shown = home.shown_modules.shown_modules(demo_hub=demo is not None)
        usable = [config for config in shown if _may_use(ctx, config)]
        return {
            "user": _user(ctx, hub_user_of(ctx)),
            "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
            "permissions": sorted(ctx.permissions),
            "menu": [
                {
                    "id": config.label,
                    "label": str(config.verbose_name),
                    "items": [
                        {"path": nav.path, "label": str(nav.label), "icon": nav.icon}
                        for nav in open_entries(ctx, config)
                    ],
                }
                for config in usable
                if _can_see(ctx, config) and config.label not in blocked
            ],
            "apps": [{"label": config.label, "state": _session_state(config.label, blocked, creating)} for config in usable],
            "locked": _locked(ctx, shown),
            **_role(ctx),
            "language": ctx.language,
            "demo": None if demo is None else {"expires_at": demo.expires_at},
        }


def _role(ctx: OperationContext) -> dict[str, Any]:
    """The role that rules what who asks may do, by its name, and what a manager may approve for them; nothing for an
    anonymous visitor or somebody without a role here."""
    held = signed_in_role_held(ctx)
    if held is None:
        return {"role": None, "approvable": []}
    return {"role": role_label(held), "approvable": approvable_of(ctx, held)}


def _locked(ctx: OperationContext, configs: list[Any]) -> dict[str, list[str]]:
    """Per module, the paths of its menu entries the person may not open; a module it opens entirely is absent, and
    nothing is locked to an anonymous visitor, who is sent to the login."""
    if ctx.actor is None:
        return {}
    locked = {}
    for config in configs:
        opened = {nav.path for nav in open_entries(ctx, config)}
        if closed := [nav.path for nav in config.navigation if nav.path not in opened]:
            locked[config.label] = closed
    return locked


# Not an assistant tool: what a device follows to read its own session again.
@operation(
    "base.session.access",
    kind="query",
    permission=VIEW_HOME,
    input=SessionAccessIn,
    output=SessionAccessOut,
    ai=INTERNAL,
)
def session_access(ctx: OperationContext, data: SessionAccessIn) -> dict[str, str]:
    """A fingerprint of what the session may do on this scope (its permissions, which every live re-run reads again from
    the person's role, the name of that role and what a manager may approve for them): when erplora.com or the business
    changes it, the device's open app sees the key change and reads ``base.session.me`` again, so its menu and the
    screen in front follow the new role without signing in again. A hash, so the stream carries a few bytes and only
    when it changes. The Home's permission, which every role of the business holds: a live query needs one."""
    with translation.override(ctx.language):
        role = _role(ctx)
    said = [*sorted(ctx.permissions), "", str(role["role"]), *role["approvable"]]
    return {"key": hashlib.sha256("\n".join(said).encode()).hexdigest()}


def _session_state(label: str, blocked: frozenset[str], creating: frozenset[str]) -> str:
    if label not in blocked:
        return "on"
    return "activating" if label in creating else "off"


def _demo_hub(ctx: OperationContext) -> Hub | None:
    """The demo's hub of this scope (its end, and the reference app it shows), or ``None``
    on a business's hub."""
    if ctx.scope.kind != "host":
        return None
    return Hub.objects.filter(slug=ctx.scope.key, is_demo=True).first()


def _user(ctx: OperationContext, person: HubUser | None = None) -> dict[str, str] | None:
    actor = ctx.actor
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    # The person of the business's database (base.HubUser), whose id every app's record names, so a screen tells
    # «mine» by it; without one there yet (the platform's host), the session's user. Named as in this hub: its «My
    # profile» name, else its Staff record's, else its account's.
    if person is None:
        return {"id": str(actor.pk), "label": person_label(actor)}
    staff_name = staff_names(ctx.scope, [person.username]).get(person.username, "")
    return {"id": str(person.pk), "label": person_label(actor, staff_name)}
