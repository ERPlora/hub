"""``/auth/login``, ``/auth/callback`` and ``/auth/logout``: the Hub's end of the login through the SaaS.

Django views, not ninja routes: ``/auth/login`` is where the shell's auth gate sends, and it jumps to
the SaaS's login with a fresh ``state`` (``base.auth.login_redirect``); the SaaS's page POSTs the
one-time code and that ``state`` as a form, in a top-level navigation (``response_mode=form_post`` of
OIDC, PLAN-SAAS §3.1 step 5), and all of them answer with a redirect. Like ``spa.py`` and
``health.py``, they hold no business logic: the session is opened by ``base.services``.

The callback redeems a code only with the ``state`` of this browser's jump (its cookie): otherwise
403, without asking the SaaS, with a page of the Hub that starts the login again; the cookie is left
for this browser's own login.

On the platform host (``request.platform_host``, ``hubs.erplora.com``) the same pair is the staff's
jump to the Hub admin (round 13, PLAN §18.1), which the SaaS admin's button starts here:
``/auth/login?hub=<slug>&next=/admin/hub/<slug>/`` jumps with the ``hub-admin`` audience and a
``state``; the callback wants ``next`` to be the deep link ``/admin/hub/<slug>/`` of a hub and that
``state``, redeems the code with the ``hub-admin`` audience for that slug, and a failure goes back to
the SaaS admin's Hubs page.

On a demo's host (``request.hub.is_demo``, plan 2026-10-17 §1.6) there is no account behind the session: the login
jumps to the SaaS's ``/demo/enter/`` (``base.auth.demo_login_redirect``) with the same ``state``, the callback, with
that ``state``, redeems a code the Hub made itself for the browser that owns the demo (``base.services``, never the
SaaS) and opens the session of the demo's owner; a code that opens nothing goes back to the SaaS's demo door
(``/demo/?state=failed``), and leaving the demo too (``/demo/``).

Every callback refused for its code or its state counts against the caller (``base.throttle.client_key``: its address,
or its IPv6 /64): past :data:`CALLBACK_ATTEMPTS`, its next refused callback is answered 429 with ``Retry-After`` and a
page of the Hub until the window of the first refusal ends. A good code always redeems, so nobody behind the same
address is locked out; it is not counted, nor what fails on the platform's side (the SaaS away, the Hub's signature) or
after a good code (a role or a user that cannot enter here).
"""

import json
import logging
import math
import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.middleware.csp import get_nonce
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.cache import add_never_cache_headers
from django.utils.translation import gettext
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_safe
from live.errors import OperationError
from live.slugs import validate_hub_slug

from base import access, auth, queries, services
from base.models import SessionOwner
from base.operations import HostScopeResolver
from base.throttle import AttemptLimit, client_key

logger = logging.getLogger(__name__)

USER_INACTIVE = "user_inactive"
#: The platform host's callback got a ``next`` that is no hub's deep link.
INVALID_NEXT = "invalid_next"
#: erplora.com's «Sign out of erplora.com?» (saas ``accounts/frontend/pages/SignOutPage.vue``, ACCOUNTS-F09): it asks
#: before closing its own session, since a redirect is a GET and a GET never signs anybody out. Not allauth's old
#: ``/accounts/logout/``, a 404 since the SaaS runs headless (saas ``accounts/tests/test_login.py``).
SAAS_LOGOUT_PATH = "/logout"
#: The 403 of a callback without this browser's state, with a link to sign in again.
LOGIN_RETRY_TEMPLATE = "base/login_retry.html"
#: The 429 of a refused callback from a caller past :data:`CALLBACK_ATTEMPTS`.
TOO_MANY_ATTEMPTS_TEMPLATE = "base/too_many_attempts.html"
#: The page of a page load without a session on its way to erplora.com, which keeps the link's fragment.
JUMP_TEMPLATE = "base/jump.html"
#: Refused callbacks per caller: 10 within 5 minutes of the first (README, «Límites de intentos»).
CALLBACK_ATTEMPTS = AttemptLimit("callback", attempts=10, window=300)
_DEEP_LINK_RE = re.compile(r"/admin/hub/(?P<slug>[^/]+)/")


@require_safe
@never_cache
def auth_login(request: HttpRequest) -> HttpResponseRedirect:
    """``/auth/login?next=<path>``: the jump to the SaaS's login of this hub, with a fresh ``state``."""
    if getattr(request, "platform_host", False):
        return _admin_login(request)
    next_path = safe_next(request.GET.get("next"))
    if request.GET.get("account"):
        # «Enter with your account» of the hub's Access page: erplora.com's sign-in, whatever the device offers.
        slug = HostScopeResolver().resolve(request).key
        return auth.demo_login_redirect(slug, next_path) if _is_demo(request) else auth.login_redirect(slug, next_path)
    return way_in(request, next_path)


def _is_demo(request: HttpRequest) -> bool:
    """Whether the request is on a demo's host (``base.middleware`` leaves the registry's row on ``request.hub``)."""
    hub = getattr(request, "hub", None)
    return hub is not None and hub.is_demo


def _admin_login(request: HttpRequest) -> HttpResponseRedirect:
    """The staff's jump to the Hub admin of ``?hub=`` (else the hub of a deep link ``next``), back on its deep link."""
    hub = request.GET.get("hub")
    slug = _hub_slug(hub) if hub else admin_hub_slug(request.GET.get("next"))
    if slug is None:
        # A hub-admin code is always for a hub (PLAN §18.1.3): the staff choose it on the SaaS admin's Hubs page.
        return HttpResponseRedirect(auth.admin_hubs_url())
    return auth.login_redirect(slug, f"/admin/hub/{slug}/", audience=auth.HUB_ADMIN_AUDIENCE)


# csrf_exempt: the form comes from the SaaS's origin, without this hub's CSRF token. What protects
# it is the state of this browser's jump (login CSRF) and the code: single-use, 60 s, for this hub,
# and redeemed server-side with a signed call.
@csrf_exempt
@require_POST
@never_cache
def auth_callback(request: HttpRequest) -> HttpResponse:
    if getattr(request, "platform_host", False):
        return _admin_callback(request)
    slug = HostScopeResolver().resolve(request).key
    next_path = safe_next(request.POST.get("next"))
    if not auth.state_matches(request, request.POST.get("state")):
        logger.warning("Login on hub %r refused: the state is not this browser's (missing, expired or another one).", slug)
        return _refused_attempt(request) or _sign_in_again(next_path)
    if _is_demo(request):
        return _demo_callback(request, request.hub, next_path)
    result = auth.redeem_code(request.POST.get("code"), slug)
    if not result.ok:
        return (result.refused and _refused_attempt(request)) or auth.login_redirect(slug, next_path, error=result.error)
    try:
        services.open_session_from_saas(request, result.user, slug)
    except services.InactiveUser:
        logger.warning("Login on hub %r refused: the hub's user %r is deactivated.", slug, result.user.user_id)
        return auth.login_redirect(slug, next_path, error=USER_INACTIVE)
    landing = _choose_a_pin_first(request, next_path, slug)
    # The language chosen in «My profile», else the account's on erplora.com (BASE-G125).
    language = queries.chosen_language(request.user) or result.user.locale
    return with_device(request, auth.forget_state(_with_language(HttpResponseRedirect(landing), language)))


def _demo_callback(request: HttpRequest, hub, next_path: str) -> HttpResponseRedirect:
    """A demo's code, redeemed here (never by the SaaS): the owner's session and ``next``, else the SaaS's door."""
    redeemed = services.redeem_demo_code(hub.slug, request.POST.get("code"))
    if redeemed is None:
        logger.warning(
            "Demo login on %r refused: the code is missing, spent, out of its minute or another demo's.", hub.slug
        )
        return _refused_attempt(request) or auth.forget_state(HttpResponseRedirect(auth.demo_failed_url()))
    try:
        services.open_demo_session(request, hub)
    except services.InactiveUser:
        logger.warning("Demo login on %r refused: its owner was deactivated.", hub.slug)
        return auth.forget_state(HttpResponseRedirect(auth.demo_failed_url()))
    return auth.forget_state(_with_language(HttpResponseRedirect(next_path), redeemed.language))


def _refused_attempt(request: HttpRequest) -> HttpResponse | None:
    """A refused callback: the 429 when its caller is already past :data:`CALLBACK_ATTEMPTS`, else counted (``None``)."""
    caller = client_key(request)
    wait = CALLBACK_ATTEMPTS.wait(caller)
    if wait:
        return _too_many_attempts(wait)
    CALLBACK_ATTEMPTS.failed(caller)
    return None


def _too_many_attempts(wait: int) -> HttpResponse:
    """429 with ``Retry-After`` and a page of the Hub (no request, no database) that says how long to wait."""
    page = render_to_string(TOO_MANY_ATTEMPTS_TEMPLATE, {"minutes": math.ceil(wait / 60)})
    response = HttpResponse(page, status=429)
    response["Retry-After"] = str(wait)
    return response


def _sign_in_again(next_path: str) -> HttpResponseForbidden:
    """403 with a page of the Hub (no request, no database) whose link starts the login again."""
    retry_url = f"{reverse('auth-login')}?{urlencode({'next': next_path})}"
    return HttpResponseForbidden(render_to_string(LOGIN_RETRY_TEMPLATE, {"retry_url": retry_url}))


def _admin_callback(request: HttpRequest) -> HttpResponse:
    """The staff's jump to the Hub admin: a ``hub-admin`` code for the hub of the deep link."""
    next_path = request.POST.get("next")
    slug = admin_hub_slug(next_path)
    if slug is None:
        error = OperationError(gettext("next must be the deep link /admin/hub/<slug>/ of a hub."), code=INVALID_NEXT)
        return JsonResponse(error.envelope(), status=error.status)
    if not auth.state_matches(request, request.POST.get("state")):
        logger.warning("Hub admin entry for hub %r refused: the state is not this browser's (missing, expired or another one).", slug)
        return _refused_attempt(request) or _sign_in_again(next_path)
    result = auth.redeem_code(request.POST.get("code"), slug, audience=auth.HUB_ADMIN_AUDIENCE)
    if not result.ok:
        return (result.refused and _refused_attempt(request)) or HttpResponseRedirect(auth.admin_hubs_url(result.error))
    try:
        services.open_admin_session_from_saas(request, result.user)
    except services.InactiveUser:
        logger.warning("Hub admin entry refused: the hub's user %r is deactivated.", result.user.user_id)
        return HttpResponseRedirect(auth.admin_hubs_url(USER_INACTIVE))
    logger.info("Hub admin session opened for SaaS user %r (%s) on hub %r.", result.user.user_id, result.user.role, slug)
    return auth.forget_state(_with_language(HttpResponseRedirect(next_path), result.user.locale))


def admin_hub_slug(value: str | None) -> str | None:
    """The hub's slug if ``value`` is exactly its deep link ``/admin/hub/<slug>/``; else ``None``."""
    match = _DEEP_LINK_RE.fullmatch(value or "")
    return None if match is None else _hub_slug(match["slug"])


def _hub_slug(value: str) -> str | None:
    """``value`` if it is a hub's slug (``live.slugs``: not reserved, valid label); else ``None``."""
    try:
        return validate_hub_slug(value)
    except ValueError:
        return None


def _with_language(response: HttpResponse, locale: str) -> HttpResponse:
    """``response`` with the language cookie of ``locale`` when the Hub has that language."""
    language = _supported_language(locale)
    if language is not None:
        translation.activate(language)
        with_language_cookie(response, language)
    return response


def with_language_cookie(response: HttpResponse, language: str) -> None:
    """Leave Django's language cookie of ``language`` on ``response`` (the login's, «My profile»'s preferences)."""
    if _supported_language(language) is not None:
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


@require_POST
def auth_logout(request: HttpRequest) -> HttpResponseRedirect:
    """Close the Hub's session, then on to the SaaS's page that asks whether to close its own (``SAAS_LOGOUT_PATH``); a
    demo's goes back to the demo door. On a device with the PIN pad (BASE-G61) it goes back to the hub's Access: the
    next person enters with their PIN, and erplora.com's session in this browser is whoever made it a device's, not the
    person signing out."""
    demo = _is_demo(request)
    pin_pad = not demo and _hub_slug_of(request) is not None and queries.pin_door_open(request, _hub_slug_of(request))
    logout(request)
    if pin_pad:
        return HttpResponseRedirect(ACCESS_PAGE)
    return HttpResponseRedirect(auth.saas_url(auth.DEMO_DOOR_PATH if demo else SAAS_LOGOUT_PATH))


def with_device(request: HttpRequest, response: HttpResponse) -> HttpResponse:
    """``response`` with the cookie of this browser's device when the entry left its token (``base.services``)."""
    token = getattr(request, access.DEVICE_TOKEN_ATTR, None)
    if token:
        access.set_device_cookie(response, token, secure=settings.SESSION_COOKIE_SECURE)
    return response


def safe_next(value: str | None) -> str:
    """``value`` if it is a path of this hub; else ``/``. Never another origin (open redirect), nor anything that is
    not text (the PIN pad's JSON body can carry whatever its sender puts in ``next``)."""
    if isinstance(value, str) and value.startswith("/") and url_has_allowed_host_and_scheme(value, allowed_hosts=None):
        return value
    return "/"


def _supported_language(locale: str) -> str | None:
    try:
        return translation.get_supported_language_variant(locale) if locale else None
    except LookupError:
        return None


# ── The way in on a device of the hub: the PIN and the badge (APP-BASE-3) ─────────────────────────────────────────

#: The hub's «Access» (``base/frontend/routes.ts``): the PIN pad, «Enter with your account» and what happened.
ACCESS_PAGE = "/login"
#: «Choose your PIN» after an entry with the account on a device that asks (BASE-G54).
PIN_SETUP_PAGE = "/pin/setup"
#: What the Access page tells (``?notice=``): the session ended, or another device's entry ended it.
NOTICE_ENDED = "ended"
NOTICE_DEVICE_LIMIT = "device_limit"


def way_in(request: HttpRequest, next_path: str) -> HttpResponseRedirect:
    """Where a browser without a session goes to enter this hub (BASE-G55, G57, G58): the hub's Access page
    (:func:`access_page_url`), else erplora.com's sign-in for this hub, as always, which brings the person straight
    back while its own session lives (a demo, its own door)."""
    access_page = access_page_url(request, next_path)
    if access_page is not None:
        return HttpResponseRedirect(access_page)
    slug = HostScopeResolver().resolve(request).key
    return auth.demo_login_redirect(slug, next_path) if _is_demo(request) else auth.login_redirect(slug, next_path)


def access_page_url(request: HttpRequest, next_path: str) -> str | None:
    """The hub's Access page for a browser without a session, or ``None``: when it is a shared device of the hub of a
    business that asks, with somebody to choose (telling, if so, that the session ended), or when another device's
    entry ended this one (the plan covers fewer devices). Never on a demo's host."""
    if _is_demo(request):
        return None
    notice = _notice(request)
    if notice == NOTICE_DEVICE_LIMIT or queries.pin_door_open(request, HostScopeResolver().resolve(request).key):
        return f"{ACCESS_PAGE}?{urlencode({'next': next_path, **({'notice': notice} if notice else {})})}"
    return None


def jump_page(request: HttpRequest, next_path: str) -> HttpResponse:
    """The page a page load without a session answers when it goes on to erplora.com or a demo's door (BASE-G52): its
    script sends to :func:`auth_login` with the fragment of the link (``/settings#data``), which the browser never
    sends to the server and the way back through erplora.com would lose; ``/auth/login`` jumps on with a fresh state.
    Never cached (it carries the response's CSP nonce)."""
    target = f"{reverse('auth-login')}?{urlencode({'next': next_path})}"
    response = HttpResponse(render_to_string(JUMP_TEMPLATE, {"target": target, "csp_nonce": get_nonce(request)}))
    add_never_cache_headers(response)
    return response


def _notice(request: HttpRequest) -> str:
    """Why this browser has no session, when it had one: another device's entry ended it, or it ended (it expired, it
    was revoked, its device removed): the session cookie came and no session answers it."""
    device = queries.device_of(request)
    if device is not None and device.ended_reason == device.EndedReason.DEVICE_LIMIT:
        return NOTICE_DEVICE_LIMIT
    if settings.SESSION_COOKIE_NAME in request.COOKIES and not request.user.is_authenticated:
        return NOTICE_ENDED
    return ""


def _choose_a_pin_first(request: HttpRequest, next_path: str, slug: str) -> str:
    """``next`` after an entry with the account, or «Choose your PIN» first (BASE-G54) when this device asks, the
    business already enters its tills by PIN (somebody else of it has one) and the person has none yet. The page lets
    them leave it for later. A business nobody of which has a PIN is never asked: its first PIN is chosen in «My
    profile» or given in Personal, as Square and Toast hand out their passcodes."""
    device = queries.device_of_entry(request)
    if device is None or not access.pin_offered(device.mode, queries.access_settings().pin_policy):
        return next_path
    me = request.user.get_username()
    if queries.has_pin(request.user) or not queries.pin_people(slug, exclude=me):
        return next_path
    return f"{PIN_SETUP_PAGE}?{urlencode({'next': next_path})}"


def _hub_slug_of(request: HttpRequest) -> str | None:
    hub = getattr(request, "hub", None)
    return hub.slug if hub is not None else None
# Django views like the callback, not ninja routes: they open a session (``login`` needs the request), which no
# operation does. JSON in and out, from the SPA's PIN pad, behind Django's CSRF check (the SPA's ``X-CSRFToken``).


@require_POST
@never_cache
def auth_pin(request: HttpRequest) -> HttpResponse:
    """``POST /auth/pin {person, pin, next}``: the session of the person of this hub whose PIN it is (BASE-G55, G60).

    In this order (the old Hub's HUB-F133): the address is not braked, the browser is a shared device of the hub of a
    business that asks, the person is not braked and the PIN is the right one of an active person of this hub. A
    wrong one counts against the person and the address; a right one starts the person's count again."""
    door = _device_door(request)
    if isinstance(door, HttpResponse):
        return door
    slug, device, body = door
    person = str(body.get("person", ""))[:64]
    wait = access.PIN_PERSON_LIMIT.wait(slug, person)
    if wait:
        return _pin_too_many(wait)
    user = queries.pin_owner(slug, person, str(body.get("pin", ""))[:16])
    if user is None:
        access.PIN_PERSON_LIMIT.failed(slug, person)
        access.PIN_ADDRESS_LIMIT.failed(slug, client_key(request))
        return _refused(401, "base.pin_incorrect", gettext("Wrong PIN."))
    access.PIN_PERSON_LIMIT.clear(slug, person)
    return _entered(request, user, device, SessionOwner.Credential.PIN, slug, body)


def _device_door(request: HttpRequest):
    """The hub, the device and the body of a PIN or badge entry, or the response that refuses it."""
    if getattr(request, "platform_host", False):
        raise Http404("The platform host has no PIN pad.")
    slug = HostScopeResolver().resolve(request).key
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _refused(422, "base.invalid_payload", gettext("The request could not be read."))
    wait = access.PIN_ADDRESS_LIMIT.wait(slug, client_key(request))
    if wait:
        return _pin_too_many(wait)
    device = queries.device_of(request)
    if device is None:
        return _refused(
            403,
            "base.device_not_trusted",
            gettext("This device does not work with a PIN yet. Sign in once here with your account and from then on it will."),
        )
    if not access.pin_offered(device.mode, queries.access_settings().pin_policy):
        return _refused(403, "base.pin_not_offered", gettext("This device does not ask for a PIN: sign in with your account."))
    return slug, device, body


def _entered(request: HttpRequest, user, device, credential: str, slug: str, body: dict) -> HttpResponse:
    services.open_session_on_device(request, user, device, credential)
    response = JsonResponse({"next": safe_next(body.get("next"))})
    return _with_language(response, queries.language_of(user, slug))


def _refused(status: int, code: str, message: str) -> JsonResponse:
    error = OperationError(message, code=code, status=status)
    return JsonResponse(error.envelope(), status=error.status)


def _pin_too_many(wait: int) -> JsonResponse:
    response = _refused(429, "base.too_many_attempts", services.too_many_message(wait, gettext("Too many wrong attempts.")))
    response["Retry-After"] = str(wait)
    return response



@require_POST
@never_cache
def auth_badge(request: HttpRequest) -> HttpResponse:
    """``POST /auth/badge {badge, next}``: the session of the person of this hub whose card it is (BASE-G56). The same
    door and brakes as the PIN's, counted against the card (its digest) instead of a person."""
    door = _device_door(request)
    if isinstance(door, HttpResponse):
        return door
    slug, device, body = door
    user, card = services.badge_owner(slug, str(body.get("badge", ""))[:128])
    wait = access.PIN_PERSON_LIMIT.wait(slug, "badge", card)
    if wait:
        return _pin_too_many(wait)
    if user is None:
        access.PIN_PERSON_LIMIT.failed(slug, "badge", card)
        access.PIN_ADDRESS_LIMIT.failed(slug, client_key(request))
        return _refused(
            401, "base.badge_unknown", gettext("That badge opens nothing here. Enter with your PIN or ask an administrator.")
        )
    access.PIN_PERSON_LIMIT.clear(slug, "badge", card)
    return _entered(request, user, device, SessionOwner.Credential.BADGE, slug, body)
