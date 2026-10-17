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
``request.hub``. The platform host ``hubs.<domain>`` (``settings.PLATFORM_HOST_LABEL``) is no hub either: it is
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
``/healthz``, static files…) never reaches the SPA view. A request that does not ask for HTML gets
the shell, whose auth gate sends to ``/auth/login``, the same jump. On a demo's host the jump is the demo's, to the
SaaS's ``/demo/enter/`` (``base.auth.demo_login_redirect``, plan 2026-10-17 §1.6): there is no account to log in to.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.urls import get_script_prefix, reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext
from live.api_errors import DEFAULT_API_PREFIX
from live.errors import NotFound

from base import registry
from base.auth import admin_hubs_url, demo_login_redirect, login_redirect, saas_url
from base.health import READYZ_PATH
from base.models import Hub
from base.operations import HostScopeResolver, is_platform_host
from base.spa import spa

#: The page of a hub that is gone (410) and of one being prepared (503); no request, no scripts (strict CSP).
HUB_GONE_TEMPLATE = "base/hub_gone.html"
HUB_PREPARING_TEMPLATE = "base/hub_preparing.html"
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
        if registry.is_gone(hub) and not (hub.is_demo and path == DEMO_ENTRY_PATH):
            return self._gone(request, hub)
        if registry.is_preparing(hub):
            return self._preparing(request)
        request.hub = hub
        return None

    def _not_found(self, request: HttpRequest) -> HttpResponse:
        if _is_api(request):
            # The envelope of an unknown API path (live.api_errors), in the request's language.
            error = NotFound(gettext("Not found"))
            return JsonResponse(error.envelope(), status=error.status)
        raise Http404("This host is no hub's.")

    def _gone(self, request: HttpRequest, hub: Hub) -> HttpResponse:
        if _wants_envelope(request):
            return _envelope(410, "base.hub_gone", gettext("This hub is no longer available."))
        back = saas_url(DEMO_ENDED_PATH if hub.is_demo else LAUNCH_PATH)
        html = render_to_string(HUB_GONE_TEMPLATE, {"is_demo": hub.is_demo, "back_url": back})
        return HttpResponse(html, status=410)

    def _preparing(self, request: HttpRequest) -> HttpResponse:
        if _wants_envelope(request):
            response = _envelope(
                503, "base.hub_preparing", gettext("This hub is still being prepared; try again in a few seconds.")
            )
        else:
            response = HttpResponse(render_to_string(HUB_PREPARING_TEMPLATE), status=503)
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
        slug = HostScopeResolver().resolve(request).key
        hub = getattr(request, "hub", None)
        if hub is not None and hub.is_demo:
            return demo_login_redirect(slug, request.get_full_path())
        return login_redirect(slug, request.get_full_path())
