"""The Hub's request gates: ``HubHostRequiredMiddleware``, ``PlatformHostMiddleware`` and ``SaasLoginRequiredMiddleware``.

``HubHostRequiredMiddleware``: a host that is no hub (``HostScopeResolver`` with ``live.slugs``: a reserved name
such as ``hub`` or ``www``, an invalid label, the bare host, an IP) answers 404 on every hub path (the SPA,
``/api``, ``/auth``…), before ninja's session auth, so an anonymous API call gets the 404 envelope and not a 401.
Then the registry decides (``base.registry``, plan 2026-10-17, §1.2): a slug without a row is 404 too; a hub that is
gone (cancelled, purged, or a demo past its ``expires_at``) is 410, a page with the way back to ERPlora (the SaaS's
``/demo/?state=expired``, or its ``/launch``), save a demo's ``/auth/login``, whose jump is how the SaaS's
``/demo/`` learns that it ended (plan 2026-10-17, §1.7); one still being prepared is 503 with ``Retry-After``, a
page that refreshes itself. The API, and any call that does not ask for a page (``Accept`` without ``text/html``),
gets the envelope instead (``base.hub_gone``, ``base.hub_preparing``). A hub that answers is left on
``request.hub``; one the SaaS's photo says is suspended for an unpaid invoice is 402 (``base.hub_suspended``), with
a session or without and its login included, until the photo says it is paid. The platform host ``hubs.<domain>`` (``settings.PLATFORM_HOST_LABEL``) is no hub either: it is
marked ``request.platform_host`` and left to ``PlatformHostMiddleware``. The Hub admin lives only there (PLAN
§18.1.3): on any other host, a hub's or not, ``/admin/`` answers 404, never the admin's own login. Static files, CSP
reports and ``/readyz`` (Route 53 and the deploy probe it on the platform host and on the private name) and
``/internal/`` (the SaaS's calls, signed: ``base.internal``) are left alone on every host.

Every gate looks at ``request.path_info``, the path Django resolves: ``request.path`` also carries the
script prefix, which behind Daphne comes from the client's own ``Daphne-Root-Path`` header, so a made-up
prefix would walk past a check made on it.

``PlatformHostMiddleware``: the platform host is only the Hub admin for the staff (round 13, PLAN
§18.1). Without a session, the staff go to the SaaS admin's Hubs page, where the jump with a
``hub-admin`` code starts (no login of its own); with a session but no staff, 403, never the login
(it would loop through the SaaS); staff outside ``/admin/`` go to ``/admin/``. ``/auth/*`` (the
callback and the logout), static files, CSP reports, ``/internal/`` (signed), ``/readyz`` (exactly that path) and
``/healthz`` (answered before any of this) are left alone. The SPA and the API never answer on this host.

``SaasLoginRequiredMiddleware``: the Hub has no login of its own; the login is the SaaS's.

A browser without a session that loads a SPA route jumps to the SaaS's ``/hub-login/`` for this hub
(PLAN-SAAS §3.1 step 4) with a fresh ``state`` in its cookie (``base.auth.login_redirect``), and the
SaaS comes back with a one-time code and that ``state`` to ``/auth/callback``. Only page loads of the
SPA are redirected: anything with a URL of its own in Django (``/api`` answers 401, ``/auth``,
``/healthz``, static files…) never reaches the SPA view, nor does a path that names a file (``/robots.txt``: a plain
404 with no cookie, ``base.spa.NOT_A_FILE``). A request that does not ask for HTML gets
the shell, whose auth gate sends to ``/auth/login``, the same jump. On a demo's host the jump is the demo's, to the
SaaS's ``/demo/enter/`` (``base.auth.demo_login_redirect``, plan 2026-10-17 §1.6): there is no account to log in to.
``/`` of a hub with a published website is that website instead (``base.public_home``, round 2026-10-21). Which way in
is ``base.auth_views.way_in``'s (APP-BASE-3): a shared device of the hub with the PIN pad, or a browser whose session
ended, goes to the hub's own Access page (``/login``, which this gate leaves alone) instead of the SaaS's.

``HubDatabaseMiddleware`` (phase 2, S1; plan 2026-10-22): right after the host gate, the rest of the request runs in
its database context: ``use_hub(request.hub)`` on a hub's host; on the platform host, the hub the admin chose
(``/admin/hub/<slug>/``) or, with none, phase 1's shared database; nothing for ``/internal`` and the open paths,
whose code opens its own. A hub's database that says it is another hub (``base.tenancy.identity``) answers 503
(``base.hub_unavailable``), serves nothing and raises an alarm; one that cannot be reached now answers the same 503
with ``Retry-After`` and a warning.

``SessionHostMiddleware`` (phase 2, S1): a session is a session of the host it was opened on (the login notes it);
on another hub's host, or on the platform host, it is anonymous (401).
"""

import logging
from contextlib import nullcontext

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.urls import get_script_prefix, reverse
from django.dispatch import receiver
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext
from live.api_errors import DEFAULT_API_PREFIX
from live.errors import NotFound

from base import registry
from base.auth import admin_hubs_url, saas_url
from base.health import READYZ_PATH
from base.models import Hub
from base.operations import HostScopeResolver, is_platform_host
from base.public_home import website_enabled
from base.spa import spa
from base.tenancy import connections as tenancy_connections
from base.tenancy import context as tenancy_context
from base.tenancy.identity import HubIdentityMismatch

logger = logging.getLogger(__name__)

#: The page of a hub that is gone (410) and of one being prepared (503); no request, no scripts (strict CSP).
HUB_GONE_TEMPLATE = "base/hub_gone.html"
HUB_PREPARING_TEMPLATE = "base/hub_preparing.html"
#: The page of a business suspended for an unpaid invoice (402): the way back is ERPlora, where it is paid.
HUB_SUSPENDED_TEMPLATE = "base/hub_suspended.html"
#: How long a client waits before asking a hub being prepared again (``Retry-After``).
PREPARING_RETRY_AFTER_SECONDS = 30
#: Where a demo that ended sends the visitor (the SaaS's /demo/, told it ended so it forgets the demo its session still
#: holds and offers another one), and where a business that is gone does.
DEMO_ENDED_PATH = "/demo/?state=expired"
LAUNCH_PATH = "/launch"
#: The one path of a demo that ended still answered: its login jumps to the SaaS's ``/demo/enter/``, which asks for a
#: code, hears 410 and tells the visitor the demo ended (the SaaS keeps no row of a demo and is never told otherwise).
DEMO_ENTRY_PATH = "/auth/login"


class HubHostRequiredMiddleware(MiddlewareMixin):
    """Placed after ``CommonMiddleware`` (``ALLOWED_HOSTS``) and before ``AuthenticationMiddleware``."""

    ADMIN_PREFIX = "/admin/"
    # /internal is the SaaS's: its signature is the authentication (base.internal), on any host.
    OPEN_PREFIXES = ("/static/", "/csp-report/", "/internal/")

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        request.platform_host = is_platform_host(request)
        if request.platform_host:
            return None
        path = request.path_info
        if path.startswith(self.ADMIN_PREFIX):
            # Before resolving the hub, so a host that is no hub gets the same 404.
            raise Http404("The Hub admin is only on the platform host.")
        if path.startswith(self.OPEN_PREFIXES) or path == READYZ_PATH:
            return None
        try:
            scope = HostScopeResolver().resolve(request)
        except Http404:
            return self._not_found(request)
        hub = registry.hub_by_slug(scope.key)
        if hub is None:
            return self._not_found(request)
        refusal = registry.refusal(hub, ended=not (hub.is_demo and path == DEMO_ENTRY_PATH))
        if refusal is not None:
            return self._refuse(request, hub, refusal)
        request.hub = hub
        return None

    def _not_found(self, request: HttpRequest) -> HttpResponse:
        if _is_api(request):
            # The envelope of an unknown API path (live.api_errors), in the request's language.
            error = NotFound(gettext("Not found"))
            return JsonResponse(error.envelope(), status=error.status)
        raise Http404("This host is no hub's.")

    def _refuse(self, request: HttpRequest, hub: Hub, refusal: registry.Refusal) -> HttpResponse:
        """The registry's refusal: its envelope, or its page for a browser (gone, being prepared, suspended)."""
        if _wants_envelope(request):
            response = _envelope(refusal.status, refusal.code, refusal.message)
        elif refusal.code == registry.HUB_GONE:
            back = saas_url(DEMO_ENDED_PATH if hub.is_demo else LAUNCH_PATH)
            html = render_to_string(HUB_GONE_TEMPLATE, {"is_demo": hub.is_demo, "back_url": back})
            response = HttpResponse(html, status=refusal.status)
        elif refusal.code == registry.HUB_PREPARING:
            response = HttpResponse(render_to_string(HUB_PREPARING_TEMPLATE), status=refusal.status)
        else:
            html = render_to_string(HUB_SUSPENDED_TEMPLATE, {"back_url": saas_url(LAUNCH_PATH)})
            response = HttpResponse(html, status=refusal.status)
        if refusal.code == registry.HUB_PREPARING:
            response["Retry-After"] = str(PREPARING_RETRY_AFTER_SECONDS)
        return response


def _is_api(request: HttpRequest) -> bool:
    api_prefix = getattr(settings, "LIVE", {}).get("api_prefix", DEFAULT_API_PREFIX).rstrip("/") + "/"
    return request.path_info.startswith(api_prefix)


def _wants_envelope(request: HttpRequest) -> bool:
    """The API, and any call that does not ask for a page, gets the JSON envelope; a browser gets the page."""
    return _is_api(request) or "text/html" not in request.headers.get("Accept", "")


def _envelope(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


class PlatformHostMiddleware(MiddlewareMixin):
    """Placed after ``AuthenticationMiddleware`` (it reads ``request.user``) and before ``SaasLoginRequiredMiddleware``."""

    OPEN_PREFIXES = ("/auth/", "/static/", "/csp-report/", "/internal/")

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        path = request.path_info
        open_path = path.startswith(self.OPEN_PREFIXES) or path == READYZ_PATH
        if not getattr(request, "platform_host", False) or open_path:
            return None
        if not request.user.is_authenticated:
            return HttpResponseRedirect(admin_hubs_url())
        if not request.user.is_staff:
            raise PermissionDenied("The Hub admin is only for the platform's staff.")
        if path == _route("admin:login"):
            # The admin's own login is off on this host: the staff enter from the SaaS admin.
            return HttpResponseRedirect(admin_hubs_url())
        if not path.startswith(_route("admin:index")):
            return HttpResponseRedirect(reverse("admin:index"))
        return None


def _route(name: str) -> str:
    """``reverse(name)`` without the script prefix, the form ``request.path_info`` has."""
    return "/" + reverse(name).removeprefix(get_script_prefix())


class SaasLoginRequiredMiddleware(MiddlewareMixin):
    """Placed after ``AuthenticationMiddleware``: it reads ``request.user``."""

    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs) -> HttpResponse | None:
        if view_func is not spa or request.user.is_authenticated:
            return None
        if request.method not in ("GET", "HEAD") or "text/html" not in request.headers.get("Accept", ""):
            return None
        if request.path_info == "/" and website_enabled(request):
            # The hub's published website is its home page for a visitor (base.public_home); staff sign in from it.
            return None
        from base.auth_views import ACCESS_PAGE, way_in

        if request.path_info == ACCESS_PAGE:
            # The hub's Access page (APP-BASE-3) is the SPA's own way in: it never jumps anywhere by itself.
            return None
        return way_in(request, request.get_full_path())


#: What the platform host runs in without a hub chosen for the admin (phase 1's one database, S1–S4).
_SHARED = object()


class HubDatabaseMiddleware:
    """Placed right after ``HubHostRequiredMiddleware``: everything after it runs in the request's database context."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response) -> None:
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        try:
            resolved = self._resolve(request)
        except (HubIdentityMismatch, DatabaseError) as error:
            return self._unavailable(request, error)
        with self._entered(resolved):
            return self.get_response(request)

    async def __acall__(self, request: HttpRequest):
        try:
            if _reaches_the_database(request):
                # Reading the session and checking a database's identity reach the database: not in the event loop.
                resolved = await sync_to_async(self._resolve)(request)
            else:
                resolved = self._resolve(request)
        except (HubIdentityMismatch, DatabaseError) as error:
            return self._unavailable(request, error)
        with self._entered(resolved):
            return await self.get_response(request)

    def _resolve(self, request: HttpRequest):
        """The hub the request works on, ``_SHARED`` or ``None``; a hub's own database is registered and checked."""
        hub = getattr(request, "hub", None)
        if hub is None and getattr(request, "platform_host", False):
            hub = _admin_hub(request)
            if hub is None:
                return _SHARED
        if hub is not None and hub.db_name:
            tenancy_connections.open_hub_alias(hub)
        return hub

    @staticmethod
    def _entered(resolved):
        if resolved is _SHARED:
            return tenancy_context.use_shared_database()
        if resolved is None:
            return nullcontext()
        return tenancy_context.use_hub(resolved)

    @staticmethod
    def _unavailable(request: HttpRequest, error: Exception) -> HttpResponse:
        """503: a database that is not its hub's (an alarm), or one that cannot be reached now (it passes)."""
        hub = getattr(request, "hub", None)
        if isinstance(error, HubIdentityMismatch):
            logger.critical("base.hub_unavailable hub=%s: its database is not its own; nothing is served (%s).", hub, error)
        else:
            logger.warning("base.hub_unreachable hub=%s: its database cannot be reached now (%s).", hub, error)
        refusal = registry.unavailable()
        response = _envelope(refusal.status, refusal.code, refusal.message)
        response["Retry-After"] = str(PREPARING_RETRY_AFTER_SECONDS)
        return response


def _reaches_the_database(request: HttpRequest) -> bool:
    """Whether resolving the request's context reads the database: the admin's session, a hub's own database."""
    hub = getattr(request, "hub", None)
    return getattr(request, "platform_host", False) or (hub is not None and bool(hub.db_name))


def _admin_hub(request: HttpRequest):
    """The hub the admin chose for this session (``base.admin.open_hub``), or ``None``."""
    from base.admin import ADMIN_HUB_SESSION_KEY

    session = getattr(request, "session", None)
    slug = session.get(ADMIN_HUB_SESSION_KEY) if session is not None else None
    return registry.hub_by_slug(slug) if slug else None


# ── A session is its host's (phase 2, S1; PLAN-DB §14.2; plan 2026-10-22, §2.3) ──────────────────────────────────

#: Where the login noted the host a session was opened on: a hub's slug, or :data:`PLATFORM_SESSION_HOST`.
SESSION_HOST_KEY = "hub_host"
#: The platform host's mark (no hub's slug can be it: ``live.slugs``).
PLATFORM_SESSION_HOST = "@platform"


def session_host(request: HttpRequest) -> str | None:
    """The host a session of this request belongs to: the hub's slug, the platform host's mark, or ``None``."""
    if getattr(request, "platform_host", False):
        return PLATFORM_SESSION_HOST
    hub = getattr(request, "hub", None)
    return hub.slug if hub is not None else None


def opened_elsewhere(request: HttpRequest) -> bool:
    """Whether the request's session was opened on another host than the request's (a hub's or the platform's).

    The one rule of every way in that reads a session: ``SessionHostMiddleware`` and the print socket
    (``base.ws_print``). A session with no host noted (from before the rule) is not.
    """
    host = session_host(request)
    if host is None:
        return False
    noted = request.session.get(SESSION_HOST_KEY)
    return noted is not None and noted != host


@receiver(user_logged_in)
def note_the_sessions_host(sender, request, user, **kwargs) -> None:
    """Every login notes its host in the new session (the SaaS's jump, a demo's, the admin's)."""
    host = session_host(request) if request is not None else None
    if host is not None and hasattr(request, "session"):
        request.session[SESSION_HOST_KEY] = host


class SessionHostMiddleware(MiddlewareMixin):
    """Placed right after ``AuthenticationMiddleware``: a session opened on another host is no session here.

    Sessions stay in control's database in this phase (plan, decision 3): a session of hub B would otherwise be
    valid on A's host for a user who is a member of both. Here it is anonymous (401 on the API; on a page, the
    SaaS's login, as without a session). A session from before this rule, with no host noted, stays valid until it
    expires; ``/internal`` and the open paths, with no hub, are left alone.
    """

    def process_request(self, request: HttpRequest) -> None:
        if opened_elsewhere(request):
            request.user = AnonymousUser()

            async def anonymous():
                return request.user

            request.auser = anonymous
