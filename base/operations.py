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
Actor = the session's user; permissions from ``base.permissions``. :func:`hub_id`, :func:`is_demo_hub` and
:func:`is_platform_hub` are what the apps ask about a hub's registry (``base.registry``; a module never reads it), and
:func:`business_currency` the currency its business charges in (``base.business.get``, read as the platform). An app
runs another app's operation with :func:`call`.
This is the only piece phase 2 replaces (scope = ``use_hub``): from S1, :meth:`HubContextBuilder.enter` gives a live
re-run its hub's database (the request's own is ``base.middleware.HubDatabaseMiddleware``'s).
"""

import dataclasses
import ipaddress
import uuid
from contextlib import AbstractContextManager, nullcontext
from typing import Any

import pydantic
from django.conf import settings
from django.db import DatabaseError
from django.http import Http404, HttpRequest
from django.utils.translation import gettext
from live.context import OperationContext, Scope, system_context
from live.errors import AppInactive, InvalidPayload, NotFound, OperationError, Unauthorized
from live.operations import UnknownOperation
from live.operations import get as get_operation
from live.slugs import validate_hub_slug

from base import registry
from base.api_keys import KeyCaller
from base.approvals import Approved, consequence_context
from base.permissions import permissions_for, reload_user
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import HUB_SCOPE_KIND, use_hub
from base.tenancy.identity import HubIdentityMismatch


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
            # A demo's slug (``demo-…``) is a hub's host too; whether it answers is the registry's (base.middleware).
            validate_hub_slug(slug, allow_demo=True)
        except ValueError as exc:
            raise Http404(f"{slug!r} is no hub's slug ({exc}).") from None
        return Scope("host", slug)


def is_platform_host(request: HttpRequest) -> bool:
    """Whether the Host is the platform's (``hubs.erplora.com``, locally ``hubs.localhost:8000``)."""
    host = _host_name(request)
    return not _is_ip_address(host) and _hub_label(host) == settings.PLATFORM_HOST_LABEL


def hub_id(scope: Scope) -> uuid.UUID:
    """The id of ``scope``'s hub: the registry's ``Hub.id`` (the SaaS's UUIDv7; ``control.Hub.id`` in phase 2), the
    one that names what a module keeps for its hub outside the database (``hub-<id>/`` in ``storages["hub_files"]``).
    A scope that is no hub's host, or a slug without a row, has none: ``NotFound``."""
    found = registry.hub_id(scope.key) if scope.kind == "host" else None
    if found is None:
        raise NotFound(gettext("No hub answers on this host."))
    return found


def is_demo_hub(scope: Scope) -> bool:
    """Whether ``scope``'s hub is an ephemeral demo (PLAN-SAAS §3.5, pinned to the AEAT's test environment): the
    registry's ``is_demo`` (``base.Hub`` in phase 1, plan 2026-10-17 §1.2; ``control.Hub`` in phase 2). A scope that
    is no hub's host, or a slug without a row, is no demo."""
    return scope.kind == "host" and registry.is_demo(scope.key)


def is_platform_hub(scope: Scope) -> bool:
    """Whether ``scope``'s hub is ERPlora's own, the one that issues ERPlora's invoices (PLAN-SAAS §4;
    ``control.Hub.is_platform`` in phase 2). Phase 1 names it by its reserved slug, ``PLATFORM_HUB_SLUG``."""
    return scope.key == settings.PLATFORM_HUB_SLUG


#: The operation that answers a hub's business (``business_currency``).
BUSINESS = "base.business.get"


def business_currency(scope: Scope) -> str:
    """The currency (ISO 4217) ``scope``'s business charges in, as ``base.business.get`` answers it: its country's;
    on ERPlora's own hub, its issuer's country's (``PLATFORM_ISSUER_COUNTRY``), as its invoices; a demo without a
    country, the euro. Read as the platform: an API key holds only the permissions of what it charges, and every
    person of the hub may see it anyway. A scope that is no hub's has none: the operation's ``NotFound``, never a
    silent euro. The one question every app that charges asks (BASE-F50)."""
    read = get_operation(BUSINESS)
    return read(system_context(scope), read.input()).currency


def call(ctx: OperationContext, name: str, data: dict, *, unavailable: OperationError | None = None) -> Any:
    """Runs another app's operation ``name`` with ``data`` for the caller: the one way an app asks another for
    something (BASE-F84). Its permission and its active-app check apply, its refusals reach the caller as they are and,
    nested in a write, it runs in a savepoint, so a refusal the caller catches leaves nothing of it behind. Inside a
    command a manager approved for this request, a command of another app goes with it (``consequence_context``). An
    app absent or off is ``unavailable`` when given (the caller's own 409), else ``UnknownOperation``/``AppInactive``;
    an input it does not take is the caller's 422, as a route would answer it."""
    try:
        op = get_operation(name)
    except UnknownOperation:
        if unavailable is not None:
            raise unavailable from None
        raise
    try:
        payload = op.input.model_validate(data)
    except pydantic.ValidationError as invalid:
        fields = {".".join(map(str, error["loc"])): error["msg"] for error in invalid.errors()}
        raise InvalidPayload(next(iter(fields.values()), str(invalid)), code="invalid_payload", fields=fields) from None
    try:
        return op(consequence_context(ctx, op), payload)
    except AppInactive:
        if unavailable is not None:
            raise unavailable from None
        raise


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


class HostClosed(Unauthorized):
    """The host stopped serving the app while a live stream or the print socket held its context: the registry's
    refusal (``base.registry.refusal``), with the gate's status, code and message (402 ``base.hub_suspended``…).
    An ``Unauthorized`` because that is how live ends a stream whose right to it is gone (``bye``); its
    reconnection, like any request, then hears the gate itself."""


class SessionEnded(Unauthorized):
    """The session a live stream or the print socket was opened with ended (the SaaS revoked it, a logout): the
    stream ends (``bye``) and its reconnection, without that session, is anonymous."""


def _session_ended(request: HttpRequest | None) -> bool:
    """Whether the session ``request`` came with is gone from the session store; a request without one (the
    system's, a test's) has none to end."""
    session = getattr(request, "session", None)
    key = getattr(session, "session_key", None)
    return key is not None and not session.exists(key)


class HubContextBuilder:
    def __init__(self, resolver: HostScopeResolver | None = None) -> None:
        self.resolver = resolver or HostScopeResolver()

    def from_request(self, request: HttpRequest) -> OperationContext:
        scope = self.resolver.resolve(request)
        caller = getattr(request, "auth", None)
        if isinstance(caller, KeyCaller):
            # APP-BASE-5: a business's API key opened this published operation (``base.api_keys``): the key acts,
            # with that operation's permission and nothing more.
            return OperationContext(
                scope=scope,
                actor=caller,
                permissions=caller.permissions,
                language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
                request=request,
            )
        user: Any = getattr(request, "user", None)
        actor = user if user is not None and user.is_authenticated else None
        permissions = permissions_for(actor, scope)
        approved = getattr(request, "approved", None)
        if isinstance(approved, Approved):
            # APP-BASE-5: a manager approved this very request (``base.approvals``): its one permission more. What that
            # command asks of other apps on the way goes with it through ``call`` (``approvals.consequence_context``).
            permissions = frozenset(permissions) | {approved.permission}
        return OperationContext(
            scope=scope,
            actor=actor,
            permissions=permissions,
            language=getattr(request, "LANGUAGE_CODE", None) or settings.LANGUAGE_CODE,
            request=request,
        )

    def enter(self, ctx: OperationContext) -> AbstractContextManager:
        """The database a live re-run of ``ctx`` works on, in the executor's thread (live's ``ContextBuilder.enter``;
        phase 2, S1): ``use_hub`` of its hub, read again from the registry. A hub that stopped serving the app, or
        whose database is not its own, ends the stream (``HostClosed``); a scope that is no hub's enters nothing."""
        if ctx.scope.kind != HUB_SCOPE_KIND:
            return nullcontext()
        hub = registry.hub_by_slug(ctx.scope.key)
        refusal = registry.refusal(hub)
        if refusal is not None:
            raise HostClosed(refusal.message, code=refusal.code, status=refusal.status)
        if hub.db_name:
            try:
                tenancy_connections.open_hub_alias(hub)
            except (HubIdentityMismatch, DatabaseError):
                # Not its own (an alarm on the request's side) or unreachable now: the stream ends and reconnects.
                refusal = registry.unavailable()
                raise HostClosed(refusal.message, code=refusal.code, status=refusal.status) from None
        return use_hub(hub)

    def refresh(self, ctx: OperationContext) -> OperationContext:
        """Re-read the session, the registry, the user and its Membership, so a session that ended
        (``/internal/sessions/revoke``, a logout: ``SessionEnded``), a revocation, or a hub that stopped serving the
        app (suspended, gone, being prepared: ``HostClosed``), reaches the next live re-run."""
        if ctx.actor is None:
            return ctx
        if _session_ended(ctx.request):
            raise SessionEnded(gettext("Your session ended: sign in again."), code="base.session_ended")
        refusal = registry.refusal(registry.hub_by_slug(ctx.scope.key))
        if refusal is not None:
            raise HostClosed(refusal.message, code=refusal.code, status=refusal.status)
        return dataclasses.replace(ctx, permissions=permissions_for(reload_user(ctx.actor), ctx.scope))
