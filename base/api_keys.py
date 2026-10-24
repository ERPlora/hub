"""The business's API keys at the door of its API (APP-BASE-5; PLAN-HUB §3 «API keys», PLAN-SAAS §2.4): without the ORM.

A key's token is ``erpk_live_`` and 256 random bits, sent as ``Authorization: Bearer <token>``; the hub keeps its
SHA-256 (``base.models.ApiKey``) and its first characters. :func:`install` puts the key's door in front of the session's
on every route of the API whose operation is published (``expose_api``) and needs a caller: the key answers first
when the request carries one (the session's own door would refuse a request without its CSRF token before the key
was looked at), else the session goes on as always. A route no app publishes never opens to a key.

The door (:class:`KeyDoor`) asks ``base.services.authenticate_api_key`` (the ORM's side) for the key of the token in
the request's hub — the hub's own database: a key of another business does not exist there — and then this module's
rules: what the key may do (read reaches the published queries of an app, write its published commands), its pace
(requests a minute) and the brake on an address that tries tokens nobody issued (``AttemptLimit``, as the PIN's).
A caller that passes gets the operation's own permission and nothing more (:class:`KeyCaller`); the operation then
checks, as for anyone, the hub, the app's right and that permission.
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field

from django.core.cache import cache
from live.operations import Operation, get
from ninja import NinjaAPI
from ninja.security import HttpBearer

from base.throttle import AttemptLimit

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "erpk_live_"
#: What the screen shows of a token to tell it apart: ``erpk_live_`` and its first 8 characters.
PREFIX_LENGTH = len(TOKEN_PREFIX) + 8
#: Tokens nobody issued, from one address: 30 within 5 minutes (as ``/internal``'s bad signatures).
KEY_ADDRESS_LIMIT = AttemptLimit("api-key-address", attempts=30, window=300)
#: The cache's key of a key's requests in one minute.
PACE_KEY = "api-key-pace:{key}:{minute}"

READ, WRITE = "read", "write"
FULL, PER_APP = "full", "per_app"
MODES = (FULL, READ, WRITE, PER_APP)


def new_token() -> str:
    """A new token: the prefix and 256 bits from the system's randomness (``secrets``), URL-safe."""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def digest(token: str) -> str:
    """What the hub keeps of a token: its SHA-256, hexadecimal."""
    return hashlib.sha256(token.encode()).hexdigest()


def kind_of(op: Operation) -> str:
    """What an operation asks of a key: ``read`` for a query, ``write`` for a command."""
    return READ if op.kind == "query" else WRITE


def allows(mode: str, scopes: dict, app: str, kind: str) -> bool:
    """Whether a key of ``mode`` (and ``scopes``, per app) may ``kind`` on ``app``."""
    if mode == FULL:
        return True
    if mode in (READ, WRITE):
        return mode == kind
    granted = scopes.get(app) if isinstance(scopes, dict) else None
    return isinstance(granted, list) and kind in granted


def over_pace(key_id: object, rate_per_minute: int, *, now: float | None = None) -> bool:
    """Count one request of the key in this minute; ``True`` once it passes ``rate_per_minute``. A cache that does
    not answer (logged) lets it through: the pace is a courtesy to the business, never its availability."""
    minute = int((time.time() if now is None else now) // 60)
    pace_key = PACE_KEY.format(key=key_id, minute=minute)
    try:
        if cache.add(pace_key, 1, timeout=120):
            count = 1
        else:
            count = cache.incr(pace_key)
    except Exception:
        logger.exception("The pace of API key %s is off for this call: the cache did not answer.", key_id)
        return False
    return count > rate_per_minute


@dataclass(frozen=True)
class KeyCaller:
    """Who calls when a key does: the key, by its name. It holds the one permission of the operation it opened and
    is no person (no ``get_username``): what an app writes as «who did it» is ``str(caller)``."""

    key_id: str
    name: str
    prefix: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    is_authenticated: bool = True

    def __str__(self) -> str:
        return f"API · {self.name}"


class KeyDoor(HttpBearer):
    """The key's door of one published route: it knows the operation, so it checks what the key may do on it."""

    def __init__(self, op_name: str) -> None:
        super().__init__()
        self.op_name = op_name

    def authenticate(self, request, token: str) -> KeyCaller | None:
        if not token.startswith(TOKEN_PREFIX):
            return None
        from base import services

        return services.authenticate_api_key(request, token, get(self.op_name))


def install(api: NinjaAPI) -> list[str]:
    """Put a key's door in front of every published route of ``api`` that needs a caller; returns their operations.

    A route open to anyone (``auth=None``) is left as it is: a key adds nothing there."""
    installed = []
    for bound_router in api._get_bound_routers():
        for path_view in bound_router.path_operations.values():
            for route in path_view.operations:
                if not route.operation_id or not route.auth_callbacks:
                    continue
                op = _published(route.operation_id)
                if op is None:
                    continue
                route.auth_callbacks = [KeyDoor(op.name), *route.auth_callbacks]
                installed.append(op.name)
    return installed


def _published(name: str) -> Operation | None:
    try:
        op = get(name)
    except Exception:
        return None
    return op if op.expose_api else None
