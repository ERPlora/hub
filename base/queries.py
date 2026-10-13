"""Read operations of base."""

from typing import Any

from django.utils import translation
from live.context import OperationContext
from live.meta import module_configs
from live.operations import operation

from base.schemas import SessionMeIn, SessionMeOut


@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``module_configs``): a platform app such as ``base`` is always
    on and never shows. No permission: an anonymous visitor gets ``user: None`` and nothing else,
    which tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    with translation.override(ctx.language):
        visible = [config for config in module_configs() if _can_see(ctx, config)]
        return {
            "user": _user(ctx.actor),
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
                if config.navigation
            ],
            "apps": [{"label": config.label, "state": "on"} for config in visible],
            "language": ctx.language,
        }


def _can_see(ctx: OperationContext, config: Any) -> bool:
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    return {"id": str(actor.pk), "label": actor.get_full_name() or actor.get_username()}
