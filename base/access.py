"""The rules of the way in to a hub (APP-BASE-3): the PIN, the badge, the device and how long a session lasts.

No ORM (like ``base.home``): the writes are ``base.services``' and the reads ``base.queries``'. These are the old Hub's
rules (``crates/runtime/src/pin_policy.rs``, ``hub_users.rs``, ``identity.rs`` at 9dd38215), which follow Square,
Toast and Clover:

- The business decides whether the till asks who is selling (``pin_policy``): ``always`` (and again after
  ``pin_inactivity_minutes`` without touching it), ``per_shift`` (the factory value) or ``never``; and how many digits a
  PIN has (``pin_length``, 4 or 6: everyone types the same number, so the pad enters on the last one). A stored value
  that is not understood goes back to the factory one, never to «not asking».
- Each device decides whether it is ``shared`` (a till: the PIN is offered and a session lasts a shift, 12 h) or
  ``personal`` (one person's: no PIN, 30 days). Asking always caps any session at 1 h; the stricter of the two wins, and
  the length is fixed when the session opens.
- A PIN is the business's length, ASCII digits only and not one of the two shapes anybody tries first: one digit
  repeated (``0000``) or a straight run up or down (``1234``, ``4321``).
- A badge is what a card reader types (4 to 64 letters, digits, ``-`` or ``_``), kept only as a keyed digest
  (:func:`badge_digest`), never as its number.
- A device is known by a random token in an HttpOnly cookie of its hub's host (:data:`DEVICE_COOKIE`); the Hub keeps
  only its SHA-256 (:func:`token_digest`). The token is the proof of the device: it never leaves it.
"""

import datetime as dt
import hashlib
import hmac
import re
import secrets

from base.throttle import AttemptLimit

# ── The business's dial ──────────────────────────────────────────────────────────────────────────────────────────

ALWAYS = "always"
PER_SHIFT = "per_shift"
NEVER = "never"
PIN_POLICIES = (ALWAYS, PER_SHIFT, NEVER)
DEFAULT_PIN_POLICY = PER_SHIFT

#: The stops of «Ask again after inactivity» (minutes).
INACTIVITY_MINUTES = (1, 5, 10, 15, 30)
DEFAULT_INACTIVITY_MINUTES = 5

PIN_LENGTHS = (4, 6)
DEFAULT_PIN_LENGTH = 4


def policy_or_default(value: object) -> str:
    return value if value in PIN_POLICIES else DEFAULT_PIN_POLICY


def inactivity_or_default(value: object) -> int:
    return value if value in INACTIVITY_MINUTES else DEFAULT_INACTIVITY_MINUTES


def pin_length_or_default(value: object) -> int:
    return value if value in PIN_LENGTHS else DEFAULT_PIN_LENGTH


# ── The device ───────────────────────────────────────────────────────────────────────────────────────────────────

SHARED = "shared"
PERSONAL = "personal"
DEVICE_MODES = (SHARED, PERSONAL)

#: The cookie that names this browser to its hub (host-only, HttpOnly): a random token, the device's proof.
DEVICE_COOKIE = "hub_device"
#: As long as a browser keeps a cookie (Chrome caps an expiry at 400 days); every entry renews it.
DEVICE_COOKIE_MAX_AGE = 400 * 24 * 60 * 60
#: Where an entry leaves the token of this browser's device for its response (``base.auth_views`` sets the cookie):
#: renewed at every entry with the account, a new one when the browser had none or its device was removed.
DEVICE_TOKEN_ATTR = "hub_device_token"
#: A device nobody entered in this long is «unused» (the old Hub's cleanup, Google's and Apple's device lists).
UNUSED_AFTER = dt.timedelta(days=30)
#: The longest name the business gives a device («Bar», «Kitchen», «Office laptop»).
DEVICE_NAME_MAX_LENGTH = 60

SHARED_SESSION = dt.timedelta(hours=12)
PERSONAL_SESSION = dt.timedelta(days=30)
ALWAYS_SESSION_CAP = dt.timedelta(hours=1)


#: How the session was opened (``SessionOwner.Credential``), as ``SessionOwner`` notes it: ``base.services._log_in``
#: writes it, so an operation that touches no database (``base.support.report``) knows it was opened with the account.
#: A session opened before that has none, and none is no account (a PIN shift's too): the shell (``base.spa``) copies
#: it from ``SessionOwner`` when it loads, so the user menu and the operation say the same.
CREDENTIAL_SESSION_KEY = "credential"


def session_lifetime(mode: str, policy: str) -> dt.timedelta:
    """How long a session opened now lasts: the device's (a shift, or 30 days on a personal one), at most 1 h when the
    business always asks. An unknown mode is a shared device's."""
    lifetime = PERSONAL_SESSION if mode == PERSONAL else SHARED_SESSION
    return min(lifetime, ALWAYS_SESSION_CAP) if policy == ALWAYS else lifetime


def pin_offered(mode: str, policy: str) -> bool:
    """Whether a device in ``mode`` offers the PIN pad: a shared one, of a business that asks who is selling."""
    return mode != PERSONAL and policy != NEVER


def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """What the Hub keeps of a device's token: its SHA-256 (the token is 256 random bits: no salt needed)."""
    return hashlib.sha256(token.encode()).hexdigest()


_BROWSERS = (
    # The order matters: Edge and the iOS shells say «Chrome»/«Safari» too.
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/")),
    ("Safari", re.compile(r"\bVersion/[\d.]+.*Safari/")),
)
_SYSTEMS = (
    ("iPad", re.compile(r"\biPad\b")),
    ("iPhone", re.compile(r"\biPhone\b")),
    ("Android", re.compile(r"\bAndroid\b")),
    ("Windows", re.compile(r"\bWindows\b")),
    ("Mac", re.compile(r"\bMacintosh\b")),
    ("Linux", re.compile(r"\bLinux\b")),
)


def device_agent(user_agent: str) -> str:
    """«Chrome · Android»: how a device is recognised before the business names it; ``""`` when it says neither."""
    browser = next((name for name, pattern in _BROWSERS if pattern.search(user_agent)), None)
    system = next((name for name, pattern in _SYSTEMS if pattern.search(user_agent)), None)
    if browser is None or system is None:
        return ""
    return f"{browser} · {system}"


# ── The PIN ──────────────────────────────────────────────────────────────────────────────────────────────────────

#: Why a PIN is refused (the codes of ``base.pin_invalid``'s ``reason``).
PIN_LENGTH = "length"
PIN_DIGITS = "digits"
PIN_GUESSABLE = "guessable"

_ASCII_DIGITS = re.compile(r"[0-9]+")


def pin_problem(pin: str, length: int) -> str | None:
    """Why ``pin`` cannot be a PIN of a business whose PINs have ``length`` digits, or ``None``."""
    if not _ASCII_DIGITS.fullmatch(pin):
        return PIN_LENGTH if pin == "" else PIN_DIGITS
    if len(pin) != length:
        return PIN_LENGTH
    steps = {int(b) - int(a) for a, b in zip(pin, pin[1:])}
    if len(steps) == 1 and steps <= {-1, 0, 1}:
        return PIN_GUESSABLE
    return None


def initials(name: str) -> str:
    """The face of a person in the PIN grid: the first letter of its first two words, or ``?``."""
    words = name.split()
    return "".join(word[0] for word in words[:2]).upper() or "?"


# ── The badge ────────────────────────────────────────────────────────────────────────────────────────────────────

_BADGE = re.compile(r"[A-Za-z0-9_-]{4,64}")


def clean_badge(raw: str) -> str | None:
    """What a reader typed, as the card it names (trimmed, upper case), or ``None`` when it is no badge."""
    badge = raw.strip()
    return badge.upper() if _BADGE.fullmatch(badge) else None


def badge_digest(badge: str, *, key: bytes) -> str:
    """The index of a card: HMAC-SHA256 with the Hub's key, so nobody can build it from a card's number at will."""
    return hmac.new(key, badge.encode(), hashlib.sha256).hexdigest()


def set_device_cookie(response, token: str, *, secure: bool) -> None:
    """Leave (or renew) the device's token in this hub's cookie: host-only, HttpOnly, ``Lax`` like the session's."""
    response.set_cookie(
        DEVICE_COOKIE, token, max_age=DEVICE_COOKIE_MAX_AGE, path="/", secure=secure, httponly=True, samesite="Lax"
    )


# ── The brakes on whoever tries PINs (the old Hub's HUB-F135) ────────────────────────────────────────────────────
# ``base.throttle.AttemptLimit``s, counted in the cache (Valkey in AWS) and keyed by the hub's slug first.

#: Wrong PINs (or badges) for one person (or card): 5 within 5 minutes; a right one starts the count again.
PIN_PERSON_LIMIT = AttemptLimit("pin", attempts=5, window=300)
#: Wrong PINs or badges from one address (``base.throttle.client_key``), whoever they named: 20 within 15 minutes.
PIN_ADDRESS_LIMIT = AttemptLimit("pin-address", attempts=20, window=900)
#: Tries to choose one's own PIN: 30 an hour, the accepted ones too (a PIN «already taken» tells something).
PIN_CHANGE_LIMIT = AttemptLimit("pin-change", attempts=30, window=3600)
