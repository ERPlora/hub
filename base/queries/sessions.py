"""The SPA's own session (``base.session.me``): the user, its permissions, and the menu and apps it may see."""

from typing import Any

from django.utils import translation
from live.context import OperationContext
from live.operations import INTERNAL, operation

from base import activation, entitlement, home
from base.models import Hub, HubUser
from base.schemas import SessionMeIn, SessionMeOut

from .apps import _can_see
from .people import hub_user_of, person_label


# Not an assistant tool: the SPA's own session, read at start.
@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut, ai=INTERNAL)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``home.shown_modules``: the reference app only in development, the tests
    or a demo's hub): a platform app such as ``base`` is always on and never shows. A module its business has no
    right to (``base.entitlement``) or turned off (``base.activation``) is ``off`` and has no menu: the shell's gate
    tells why its screens do not open. ``demo`` says when the demo ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing else, which
    tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
    # Not on: a paid module without its right, or one the business turned off (base.activation); one whose tables the
    # hub's own database is still getting is «activating».
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    creating = activation.creating_apps(ctx.scope) if blocked else frozenset()
    with translation.override(ctx.language):
        visible = [config for config in home.shown_modules(demo_hub=demo is not None) if _can_see(ctx, config)]
        return {
            "user": _user(ctx.actor, hub_user_of(ctx)),
            "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
            "permissions": sorted(ctx.permissions),
            "menu": [
                {
                    "id": config.label,
                    "label": str(config.verbose_name),
                    "items": [
                        {"path": nav.path, "label": str(nav.label), "icon": nav.icon} for nav in config.navigation
                    ],
                }
                for config in visible
                if config.navigation and config.label not in blocked
            ],
            "apps": [{"label": config.label, "state": _session_state(config.label, blocked, creating)} for config in visible],
            "language": ctx.language,
            "demo": None if demo is None else {"expires_at": demo.expires_at},
        }


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


def _user(actor: Any, person: HubUser | None = None) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    # The person of the business's database (base.HubUser), whose id every app's record names, so a screen tells
    # «mine» by it; without one there yet (the platform's host), the session's user. Named as in this hub: its «My
    # profile» name, else its account's.
    return {"id": str(actor.pk if person is None else person.pk), "label": person_label(actor)}
