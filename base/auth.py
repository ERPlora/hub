"""Login through the SaaS (PLAN-SAAS §2.1, §3.1 steps 4–6): the Hub has no login of its own.

Without a session, a browser goes to the SaaS's ``/hub-login/?hub=<slug>&next=<path>``
(:func:`login_url`). The SaaS answers with a form that POSTs a one-time code to ``/auth/callback``,
and the Hub redeems it server-side (:func:`redeem_code`): ``POST {SAAS_URL}/internal/auth/redeem``
with ``{"code", "hub"}``, signed with HMAC-SHA256 over ``f"{timestamp}.{raw_body}"`` (key
``INTERNAL_SHARED_SECRET``), the scheme of Stripe's webhook signatures. The HTTP call is
:func:`post`, which tests replace.

The staff's jump to the Hub admin (round 13, PLAN §18.1) is the same exchange with the audience
``hub-admin``: it starts on the SaaS admin's Hubs page (:func:`admin_hubs_url`), lands on the
platform host's ``/auth/callback`` and answers a platform role (``platform_admin``,
``platform_support``), never a customer's.
"""

import hashlib
import hmac
import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings

from base.models import Membership

logger = logging.getLogger(__name__)

LOGIN_PATH = "/hub-login/"
#: The SaaS admin's Hubs page, where the staff's jump to the Hub admin starts and comes back on failure.
ADMIN_HUBS_PATH = "/admin/accounts/hubs/"
REDEEM_PATH = "/internal/auth/redeem"
TIMESTAMP_HEADER = "X-Erplora-Timestamp"
SIGNATURE_HEADER = "X-Erplora-Signature"
TIMEOUT_SECONDS = 5

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
    return f"{settings.SAAS_URL.rstrip('/')}{path}"


def login_url(slug: str, next_path: str | None = None, error: str | None = None) -> str:
    """The SaaS's login page for this hub; without ``next_path`` the SPA appends its own ``&next=``."""
    params = {"hub": slug}
    if next_path is not None:
        params["next"] = next_path
    if error is not None:
        params["error"] = error
    return f"{saas_url(LOGIN_PATH)}?{urlencode(params, safe='/')}"


def admin_hubs_url(error: str | None = None) -> str:
    """The SaaS admin's Hubs page: the Hub admin has no login of its own (PLAN §18.1)."""
    query = f"?{urlencode({'error': error})}" if error is not None else ""
    return f"{saas_url(ADMIN_HUBS_PATH)}{query}"


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Hex HMAC-SHA256 of ``f"{timestamp}.{body}"`` with ``secret``."""
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


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
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(settings.INTERNAL_SHARED_SECRET, timestamp, body),
    }
    try:
        status, answer = post(saas_url(REDEEM_PATH), body, headers, TIMEOUT_SECONDS)
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
