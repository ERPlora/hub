"""``/auth/callback`` and ``/auth/logout``: the Hub's end of the login through the SaaS.

Django views, not ninja routes: the SaaS's page POSTs the one-time code as a form, in a top-level
navigation (``response_mode=form_post`` of OIDC, PLAN-SAAS §3.1 step 5), and both answer with a
redirect. Like ``spa.py`` and ``health.py``, they hold no business logic: the session is opened by
``base.services``.

On the platform host (``request.platform_host``, ``hubs.erplora.com``) the callback ends the staff's
jump from the SaaS admin's Hubs page (round 13, PLAN §18.1): ``next`` must be the deep link
``/admin/hub/<slug>/`` of a hub, the code is redeemed with the ``hub-admin`` audience for that slug,
and a failure goes back to that Hubs page.
"""

import logging
import re

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import translation
from django.utils.translation import gettext
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from live.errors import OperationError
from live.slugs import validate_hub_slug

from base import auth, services
from base.operations import HostScopeResolver

logger = logging.getLogger(__name__)

USER_INACTIVE = "user_inactive"
#: The platform host's callback got a ``next`` that is no hub's deep link.
INVALID_NEXT = "invalid_next"
SAAS_LOGOUT_PATH = "/accounts/logout/"
_DEEP_LINK_RE = re.compile(r"/admin/hub/(?P<slug>[^/]+)/")


# csrf_exempt: the form comes from the SaaS's origin, without this hub's CSRF token. What protects
# it is the code: single-use, 60 s, for this hub, and redeemed server-side with a signed call.
@csrf_exempt
@require_POST
@never_cache
def auth_callback(request: HttpRequest) -> HttpResponse:
    if getattr(request, "platform_host", False):
        return _admin_callback(request)
    slug = HostScopeResolver().resolve(request).key
    next_path = safe_next(request.POST.get("next"))
    result = auth.redeem_code(request.POST.get("code"), slug)
    if not result.ok:
        return HttpResponseRedirect(auth.login_url(slug, next_path, error=result.error))
    try:
        services.open_session_from_saas(request, result.user, slug)
    except services.InactiveUser:
        logger.warning("Login on hub %r refused: the hub's user %r is deactivated.", slug, result.user.user_id)
        return HttpResponseRedirect(auth.login_url(slug, next_path, error=USER_INACTIVE))
    return _with_language(HttpResponseRedirect(next_path), result.user.locale)


def _admin_callback(request: HttpRequest) -> HttpResponse:
    """The staff's jump to the Hub admin: a ``hub-admin`` code for the hub of the deep link."""
    next_path = request.POST.get("next")
    slug = admin_hub_slug(next_path)
    if slug is None:
        error = OperationError(gettext("next must be the deep link /admin/hub/<slug>/ of a hub."), code=INVALID_NEXT)
        return JsonResponse(error.envelope(), status=error.status)
    result = auth.redeem_code(request.POST.get("code"), slug, audience=auth.HUB_ADMIN_AUDIENCE)
    if not result.ok:
        return HttpResponseRedirect(auth.admin_hubs_url(result.error))
    try:
        services.open_admin_session_from_saas(request, result.user)
    except services.InactiveUser:
        logger.warning("Hub admin entry refused: the hub's user %r is deactivated.", result.user.user_id)
        return HttpResponseRedirect(auth.admin_hubs_url(USER_INACTIVE))
    logger.info("Hub admin session opened for SaaS user %r (%s) on hub %r.", result.user.user_id, result.user.role, slug)
    return _with_language(HttpResponseRedirect(next_path), result.user.locale)


def admin_hub_slug(value: str | None) -> str | None:
    """The hub's slug if ``value`` is exactly its deep link ``/admin/hub/<slug>/``; else ``None``."""
    match = _DEEP_LINK_RE.fullmatch(value or "")
    if match is None:
        return None
    try:
        return validate_hub_slug(match["slug"])
    except ValueError:
        return None


def _with_language(response: HttpResponse, locale: str) -> HttpResponse:
    """``response`` with the language cookie of ``locale`` when the Hub has that language."""
    language = _supported_language(locale)
    if language is not None:
        translation.activate(language)
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
    return response


@require_POST
def auth_logout(request: HttpRequest) -> HttpResponseRedirect:
    """Close the Hub's session, then the SaaS's (its page asks to confirm)."""
    logout(request)
    return HttpResponseRedirect(auth.saas_url(SAAS_LOGOUT_PATH))


def safe_next(value: str | None) -> str:
    """``value`` if it is a path of this hub; else ``/``. Never another origin (open redirect)."""
    if value and value.startswith("/") and url_has_allowed_host_and_scheme(value, allowed_hosts=None):
        return value
    return "/"


def _supported_language(locale: str) -> str | None:
    try:
        return translation.get_supported_language_variant(locale) if locale else None
    except LookupError:
        return None
