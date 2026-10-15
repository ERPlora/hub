"""Context builder of hub-next phase 1 (``settings.LIVE["context_builder"]``).

Scope = the one label of the Host in front of ``settings.HUB_BASE_DOMAIN`` (``a.localhost`` → ``a``,
``acme.erplora.com`` → ``acme``) when it is a hub's slug (``live.slugs``); any other host (a reserved
name such as ``hub`` or ``www``, an invalid label, the bare host, an IP, a host of another domain such
as pre's ``acme.pre.erplora.com`` on prod's Hub) is no hub and raises ``Http404``: the SPA, the API,
``/api/live`` and ``/auth/callback`` answer 404. prod and pre share one ALB, whose wildcard
``*.erplora.com`` also matches ``*.pre.erplora.com``: the base domain keeps each Hub on its own hosts.
An empty ``HUB_BASE_DOMAIN`` takes the Host's first label wherever it is. The platform host
(``settings.PLATFORM_HOST_LABEL`` on the base domain, ``hubs.erplora.com``: the Hub admin, PLAN §18.1)
is no hub either; :func:`is_platform_host` tells it apart so ``base.middleware`` serves it the admin.
Actor = the session's user; permissions from ``base.permissions``. :func:`is_demo_hub` is what the apps
ask about a hub's registry (a module never reads it). This is the only piece phase 2 replaces (scope =
``use_hub``).
"""

import dataclasses
import ipaddress
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest
from live.context import OperationContext, Scope
from live.slugs import validate_hub_slug

from base.permissions import permissions_for, reload_user


class HostScopeResolver:
    def resolve(self, request: HttpRequest) -> Scope:
        """The hub of the request's Host; ``Http404`` if that host is no hub."""
        host = _host_name(request)
        if _is_ip_address(host):
            raise Http404("An IP address is no hub's host.")
        slug = _hub_label(host)
        if slug is None:
            raise Http404(f"{host!r} is not a host on {settings.HUB_BASE_DOMAIN!r}.")
        try:
            validate_hub_slug(slug)
        except ValueError as exc:
            raise Http404(f"{slug!r} is no hub's slug ({exc}).") from None
        return Scope("host", slug)


def is_platform_host(request: HttpRequest) -> bool:
    """Whether the Host is the platform's (``hubs.erplora.com``, locally ``hubs.localhost:8000``)."""
    host = _host_name(request)
    return not _is_ip_address(host) and _hub_label(host) == settings.PLATFORM_HOST_LABEL


def is_demo_hub(scope: Scope) -> bool:
    """Whether ``scope``'s hub is an ephemeral demo (PLAN-SAAS §3.5: ``control.Hub.is_demo``, pinned to the AEAT's
    test environment). Phase 1 has neither the control registry nor demos (block 7): no hub is one."""
    return False


def _host_name(request: HttpRequest) -> str:
    return request.get_host().split(":", 1)[0].lower()


def _hub_label(host: str) -> str | None:
    """The one label in front of ``HUB_BASE_DOMAIN`` (``acme`` of ``acme.erplora.com``), or ``None``
    when the host is not exactly one label on it; the first label when there is no base domain."""
    base_domain = settings.HUB_BASE_DOMAIN
    if not base_domain:
        return host.split(".", 1)[0]
    label, dot, rest = host.partition(".")
    return label if dot and rest == base_domain else None


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


class HubContextBuilder:
    def __init__(self, resolver: HostScopeResolver | None = None) -> None:
        self.resolver = resolver or HostScopeResolver()

    def from_request(self, request: HttpRequest) -> OperationContext:
        scope = self.resolver.resolve(request)
        user: Any = getattr(request, "user", None)
        actor = user if user is not None and user.is_authenticated else None
        return OperationContext(
            scope=scope,
            actor=actor,
            permissions=permissions_for(actor, scope),
            language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
            request=request,
        )

    def refresh(self, ctx: OperationContext) -> OperationContext:
        """Re-read the user and its Membership, so a revocation reaches the next live re-run."""
        if ctx.actor is None:
            return ctx
        return dataclasses.replace(ctx, permissions=permissions_for(reload_user(ctx.actor), ctx.scope))
