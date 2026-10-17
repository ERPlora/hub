"""Login through the SaaS (PLAN-SAAS §2.1, §3.1 steps 4–6): the Hub has no login of its own.

Without a session, a browser jumps to the SaaS's ``/hub-login/?hub=<slug>&next=<path>&state=<state>``
(:func:`login_redirect`). The SaaS answers with a form that POSTs a one-time code and that ``state``,
as it got it, to ``/auth/callback``, and the Hub redeems the code server-side (:func:`redeem_code`):
``POST {SAAS_INTERNAL_URL}/internal/auth/redeem`` with ``{"code", "hub"}``, signed v1 and v2 with HMAC-SHA256
(``base.signing.signed_headers``, key ``INTERNAL_SHARED_SECRET``), the scheme of Stripe's webhook
signatures. The HTTP call is :func:`post`, which tests replace.

The ``state`` (OAuth 2.0, RFC 6749 §10.12) binds the login to the browser that started it: the jump
leaves it in the cookie ``hub_login_state`` (signed, 600 s, only for ``/auth/callback``), and the
callback redeems no code whose ``state`` is not that one (:func:`state_matches`). Without it, a code
stolen from someone else, posted from this browser, would open their session here (login CSRF).

Two URLs of the SaaS: ``SAAS_URL`` (:func:`saas_url`) is where the browser goes; every ``/internal/*``
call goes to ``SAAS_INTERNAL_URL`` (:func:`saas_internal_url`), the private name in production,
because the ALB answers 404 to ``/internal`` from outside.

The staff's jump to the Hub admin (round 13, PLAN §18.1) is the same exchange, with its ``state``,
and the audience ``hub-admin``: the SaaS admin's button opens the platform host's
``/auth/login?hub=<slug>&next=/admin/hub/<slug>/``, which jumps to ``/hub-login/?hub=<slug>&audience=hub-admin&…``;
the code lands on the platform host's ``/auth/callback`` and answers a platform role
(``platform_admin``, ``platform_support``), never a customer's. Without a hub the staff go to the
SaaS admin's Hubs page (:func:`admin_hubs_url`), where they choose one.
"""

import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from base import signing
from base.models import Membership
# The headers' names, here too for the apps that sign their own calls to the SaaS with :func:`sign`.
from base.signing import SIGNATURE_HEADER, TIMESTAMP_HEADER

logger = logging.getLogger(__name__)

LOGIN_PATH = "/hub-login/"
#: The SaaS admin's Hubs page, where the staff's jump to the Hub admin starts and comes back on failure.
ADMIN_HUBS_PATH = "/admin/accounts/hubs/"
REDEEM_PATH = "/internal/auth/redeem"
TIMEOUT_SECONDS = 5

#: The ``state`` of this browser's jump to the SaaS's login, signed; only the callback reads it.
STATE_COOKIE = "hub_login_state"
STATE_COOKIE_PATH = "/auth/callback"
STATE_MAX_AGE = 600
_STATE_SALT = "base.auth.login_state"

# Error codes the SaaS's login page receives back in ``?error=``.
INVALID_CODE = "invalid_code"
HUB_UNAUTHORIZED = "hub_unauthorized"
SAAS_UNAVAILABLE = "saas_unavailable"
UNKNOWN_ROLE = "unknown_role"
#: A ``hub-admin`` code answered with a customer's role: no staff session.
NOT_PLATFORM_STAFF = "not_platform_staff"

#: A member enters their hub (``<slug>.erplora.com``); the SaaS's default when the body has none.
HUB_SESSION_AUDIENCE = "hub-session"
#: The platform's staff enter the Hub admin (``hubs.erplora.com``).
HUB_ADMIN_AUDIENCE = "hub-admin"

PLATFORM_ADMIN = "platform_admin"
PLATFORM_SUPPORT = "platform_support"

# The SaaS's customer roles are the Hub's, as they are (``hub_owner``, ``hub_admin``…); any role
# without the ``hub_`` prefix (a platform role, an old unprefixed one) is refused. The Hub admin
# takes only the platform's roles.
_ROLES = frozenset(Membership.Role.values)
_ROLES_BY_AUDIENCE = {
    HUB_SESSION_AUDIENCE: _ROLES,
    HUB_ADMIN_AUDIENCE: frozenset({PLATFORM_ADMIN, PLATFORM_SUPPORT}),
}
# An error code from the SaaS travels back in a URL: only a plain identifier is passed through.
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class RedeemedUser:
    """Who the SaaS says the code belongs to, with the Hub's role on this hub."""

    user_id: str
    email: str
    name: str
    locale: str
    role: str


@dataclass(frozen=True)
class RedeemResult:
    user: RedeemedUser | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None


def saas_url(path: str) -> str:
    """``path`` on the SaaS's public URL: for the browser."""
    return f"{settings.SAAS_URL.rstrip('/')}{path}"


def saas_internal_url(path: str) -> str:
    """``path`` on the SaaS's internal URL: for every server-to-server ``/internal/*`` call."""
    return f"{settings.SAAS_INTERNAL_URL.rstrip('/')}{path}"


def login_url(
    slug: str, next_path: str, *, state: str, error: str | None = None, audience: str = HUB_SESSION_AUDIENCE
) -> str:
    """The SaaS's login page for this hub, with the ``state`` the callback will ask back.

    ``audience`` travels only when it is not ``hub-session``, the SaaS's default (a member's login).
    """
    if audience not in _ROLES_BY_AUDIENCE:
        raise ValueError(f"Unknown audience {audience!r}.")
    params = {"hub": slug}
    if audience != HUB_SESSION_AUDIENCE:
        params["audience"] = audience
    params["next"] = next_path
    if error is not None:
        params["error"] = error
    params["state"] = state
    return f"{saas_url(LOGIN_PATH)}?{urlencode(params, safe='/')}"


def login_redirect(
    slug: str, next_path: str, error: str | None = None, audience: str = HUB_SESSION_AUDIENCE
) -> HttpResponseRedirect:
    """The jump to the SaaS's login with a fresh ``state``, left in this browser's cookie for the callback."""
    state = secrets.token_urlsafe(32)
    response = HttpResponseRedirect(login_url(slug, next_path, state=state, error=error, audience=audience))
    response.set_signed_cookie(
        STATE_COOKIE,
        state,
        salt=_STATE_SALT,
        max_age=STATE_MAX_AGE,
        path=STATE_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite=_state_samesite(),
    )
    return response


def state_matches(request: HttpRequest, state: str | None) -> bool:
    """Whether ``state`` is the one of this browser's jump: its cookie, signed by the Hub less than 600 s ago."""
    expected = request.get_signed_cookie(STATE_COOKIE, default=None, salt=_STATE_SALT, max_age=STATE_MAX_AGE)
    if not expected or not state:
        return False
    return secrets.compare_digest(expected.encode(), state.encode())


def forget_state(response: HttpResponse) -> HttpResponse:
    """``response``, deleting this browser's ``state``: it serves one login."""
    response.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH, samesite=_state_samesite())
    return response


def _state_samesite() -> str:
    # In production the SaaS and the hubs are one site (erplora.com, <slug>.erplora.com): its POST to
    # the callback carries a Lax cookie. Locally they are two (localhost:8001, a.localhost:8000) and only
    # a None cookie comes back, which must be Secure: Chrome and Firefox take it on http://*.localhost.
    return "None" if settings.DEBUG else "Lax"


def admin_hubs_url(error: str | None = None) -> str:
    """The SaaS admin's Hubs page: the Hub admin has no login of its own (PLAN §18.1)."""
    query = f"?{urlencode({'error': error})}" if error is not None else ""
    return f"{saas_url(ADMIN_HUBS_PATH)}{query}"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The v1 signature (hex HMAC-SHA256 of ``f"{timestamp}.{body}"`` with ``secret``), in this module's argument order.

    The apps that call the SaaS themselves (``verifactu``, ``whatsapp_inbox``) sign with it; it is
    ``base.signing.sign``, the one scheme of both projects, which new code calls (or ``signed_headers``, v1 + v2).
    """
    return signing.sign(body, int(timestamp), secret)


def post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    """POST ``body`` and return ``(status, body)``; an HTTP error status is an answer, not an exception.

    Network failures (refused, timeout, DNS) raise ``OSError`` (``URLError`` is one).
    """
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()


def redeem_code(code: str | None, slug: str, audience: str = HUB_SESSION_AUDIENCE) -> RedeemResult:
    """Ask the SaaS who the one-time ``code`` belongs to, for the hub ``slug``.

    Never raises for the SaaS's answer; an ``audience`` other than ``hub-session`` or
    ``hub-admin`` is a programming error (``ValueError``). ``hub-session`` keeps the body the SaaS
    has always received (it is its default).
    """
    if audience not in _ROLES_BY_AUDIENCE:
        raise ValueError(f"Unknown audience {audience!r}.")
    if not code or not code.strip():
        return RedeemResult(error=INVALID_CODE)
    payload = {"code": code, "hub": slug}
    if audience != HUB_SESSION_AUDIENCE:
        payload["audience"] = audience
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", REDEEM_PATH, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        status, answer = post(saas_internal_url(REDEEM_PATH), body, headers, TIMEOUT_SECONDS)
    except OSError as exc:
        logger.warning("Redeeming a login code for hub %r: the SaaS is unreachable (%s).", slug, exc)
        return RedeemResult(error=SAAS_UNAVAILABLE)
    if status == 200:
        return _user_from(answer, slug, audience)
    if status == 400:
        error = _error_code(answer) or INVALID_CODE
        logger.warning("Redeeming a login code for hub %r: the SaaS refused it (%s).", slug, error)
        return RedeemResult(error=error)
    if status in (401, 403):
        logger.warning("Redeeming a login code for hub %r: the SaaS rejected the hub's signature (%s).", slug, status)
        return RedeemResult(error=HUB_UNAUTHORIZED)
    logger.warning("Redeeming a login code for hub %r: the SaaS answered %s.", slug, status)
    return RedeemResult(error=SAAS_UNAVAILABLE)


def _json(answer: bytes) -> object:
    try:
        return json.loads(answer)
    except ValueError:
        return None


def _error_code(answer: bytes) -> str | None:
    payload = _json(answer)
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) and _ERROR_CODE_RE.match(code) else None


def _user_from(answer: bytes, slug: str, audience: str) -> RedeemResult:
    payload = _json(answer)
    user_id = payload.get("user_id") if isinstance(payload, dict) else None
    if isinstance(user_id, bool) or not isinstance(user_id, (str, int)) or str(user_id) == "":
        logger.warning("Redeeming a login code for hub %r: the SaaS's answer has no user_id.", slug)
        return RedeemResult(error=SAAS_UNAVAILABLE)
    role = payload.get("role")
    if audience == HUB_ADMIN_AUDIENCE and isinstance(role, str) and role in _ROLES:
        logger.warning("Redeeming a hub-admin code for hub %r: customer role %r, no staff session.", slug, role)
        return RedeemResult(error=NOT_PLATFORM_STAFF)
    if not isinstance(role, str) or role not in _ROLES_BY_AUDIENCE[audience]:
        logger.warning("Redeeming a %s code for hub %r: unknown role %r.", audience, slug, role)
        return RedeemResult(error=UNKNOWN_ROLE)
    return RedeemResult(
        user=RedeemedUser(
            user_id=str(user_id),
            email=_text(payload, "email"),
            name=_text(payload, "name"),
            locale=_text(payload, "locale"),
            role=role,
        )
    )


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""
