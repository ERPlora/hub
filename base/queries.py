"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``) and a demo's status
(``base.demo.get``)."""

from typing import Any

from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.meta import module_configs
from live.operations import operation

from base.models import Hub
from base.registry import hub_answer, internal_only
from base.schemas import (
    DemoSlugIn,
    DemoStatusOut,
    HubGetIn,
    HubOut,
    HubsBySlugIn,
    HubsBySlugOut,
    SessionMeIn,
    SessionMeOut,
)


@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``module_configs``): a platform app such as ``base`` is always
    on and never shows. ``demo`` says when the demo ends, on a demo's hub only. No permission: an
    anonymous visitor gets ``user: None`` and nothing else, which tells the SPA to send it to the login.
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
            "demo": _demo(ctx),
        }


def _demo(ctx: OperationContext) -> dict[str, Any] | None:
    """When the demo of this scope ends (plan 2026-10-17, §1.6), or ``None`` on a business's hub."""
    if ctx.scope.kind != "host":
        return None
    hub = Hub.objects.filter(slug=ctx.scope.key, is_demo=True).first()
    return None if hub is None else {"expires_at": hub.expires_at}


def _can_see(ctx: OperationContext, config: Any) -> bool:
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    return {"id": str(actor.pk), "label": actor.get_full_name() or actor.get_username()}


@operation("base.hub.get", kind="query", permission=None, input=HubGetIn, output=HubOut)
def hub_get(ctx: OperationContext, data: HubGetIn) -> dict[str, Any]:
    """The registry's row of ``data.id`` (``GET /internal/hubs/{id}``), for the platform only: the SaaS asks it about
    a sign-up whose ``ready`` it never heard, and marks it ready when ``status`` is ``ready``."""
    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub_answer(hub)


@operation("base.hub.by_slugs", kind="query", permission=None, input=HubsBySlugIn, output=HubsBySlugOut)
def hubs_by_slugs(ctx: OperationContext, data: HubsBySlugIn) -> dict[str, Any]:
    """The registry's status of each of ``data.slugs`` (``None`` without a row), in their order, for the platform
    only: ``seed_local_hubs --check`` asks it about ``a`` and ``b``."""
    internal_only(ctx)
    found = dict(Hub.objects.filter(slug__in=data.slugs).values_list("slug", "status"))
    return {"hubs": [{"slug": slug, "status": found.get(slug)} for slug in data.slugs]}


@operation("base.demo.get", kind="query", permission=None, input=DemoSlugIn, output=DemoStatusOut)
def demo_get(ctx: OperationContext, data: DemoSlugIn) -> dict[str, Any]:
    """The status of the demo ``data.slug``, for the platform only: ``manage.py demo_expire`` says it once done."""
    internal_only(ctx)
    hub = Hub.objects.filter(slug=data.slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}
