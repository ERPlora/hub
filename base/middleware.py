"""The Hub's request gates: ``HubHostRequiredMiddleware``, ``PlatformHostMiddleware`` and ``SaasLoginRequiredMiddleware``.

``HubHostRequiredMiddleware``: a host that is no hub (``HostScopeResolver`` with ``live.slugs``: a
reserved name such as ``hub`` or ``www``, an invalid label, the bare host, an IP) answers 404 on every
hub path (the SPA, ``/api``, ``/auth``…), before ninja's session auth, so an anonymous API call gets
the 404 envelope and not a 401. The platform host ``hubs.<domain>`` (``settings.PLATFORM_HOST_LABEL``)
is no hub either: it is marked ``request.platform_host`` and left to ``PlatformHostMiddleware``. The
Hub admin lives only there (PLAN §18.1.3): on any other host, a hub's or not, ``/admin/`` answers 404,
never the admin's own login. Static files, CSP reports and ``/readyz`` (Route 53 and the deploy probe
it on the platform host and on the private name) are left alone on every host.

Every gate looks at ``request.path_info``, the path Django resolves: ``request.path`` also carries the
script prefix, which behind Daphne comes from the client's own ``Daphne-Root-Path`` header, so a made-up
prefix would walk past a check made on it.

``PlatformHostMiddleware``: the platform host is only the Hub admin for the staff (round 13, PLAN
§18.1). Without a session, the staff go to the SaaS admin's Hubs page, where the jump with a
``hub-admin`` code starts (no login of its own); with a session but no staff, 403, never the login
(it would loop through the SaaS); staff outside ``/admin/`` go to ``/admin/``. ``/auth/*`` (the
callback and the logout), static files, CSP reports, ``/readyz`` (exactly that path) and ``/healthz``
(answered before any of this) are left alone. The SPA and the API never answer on this host.

``SaasLoginRequiredMiddleware``: the Hub has no login of its own; the login is the SaaS's.

A browser without a session that loads a SPA route jumps to the SaaS's ``/hub-login/`` for this hub
(PLAN-SAAS §3.1 step 4) with a fresh ``state`` in its cookie (``base.auth.login_redirect``), and the
SaaS comes back with a one-time code and that ``state`` to ``/auth/callback``. Only page loads of the
SPA are redirected: anything with a URL of its own in Django (``/api`` answers 401, ``/auth``,
``/healthz``, static files…) never reaches the SPA view. A request that does not ask for HTML gets
the shell, whose auth gate sends to ``/auth/login``, the same jump.
"""

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.urls import get_script_prefix, reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext
from live.api_errors import DEFAULT_API_PREFIX
from live.errors import NotFound

from base.auth import admin_hubs_url, login_redirect
from base.health import READYZ_PATH
from base.operations import HostScopeResolver, is_platform_host
from base.spa import spa


class HubHostRequiredMiddleware(MiddlewareMixin):
    """Placed after ``CommonMiddleware`` (``ALLOWED_HOSTS``) and before ``AuthenticationMiddleware``."""

    ADMIN_PREFIX = "/admin/"
    OPEN_PREFIXES = ("/static/", "/csp-report/")

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
            HostScopeResolver().resolve(request)
        except Http404:
            api_prefix = getattr(settings, "LIVE", {}).get("api_prefix", DEFAULT_API_PREFIX).rstrip("/") + "/"
            if path.startswith(api_prefix):
                # The envelope of an unknown API path (live.api_errors), in the request's language.
                error = NotFound(gettext("Not found"))
                return JsonResponse(error.envelope(), status=error.status)
            raise
        return None


class PlatformHostMiddleware(MiddlewareMixin):
    """Placed after ``AuthenticationMiddleware`` (it reads ``request.user``) and before ``SaasLoginRequiredMiddleware``."""

    OPEN_PREFIXES = ("/auth/", "/static/", "/csp-report/")

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
        return login_redirect(slug, request.get_full_path())
