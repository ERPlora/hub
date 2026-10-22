"""A fixed-window limit per key on Django's cache (Valkey in AWS, the process's memory locally), and its 429.

A route that answers without a session (a hub's public website) counts its callers with :func:`allow`, by a key of
its own (``"<app>:<hub slug>:<IP>"``, the IP by :func:`client_address`), and raises :class:`RateLimited` when it says
no: the API's error envelope, 429 ``base.rate_limited``, in the request's language. The count lives under
:data:`KEY_PREFIX` for ``window`` seconds from the window's first call; the next call after that opens a new window.

A door that checks a credential (the login's callback, ``/internal``'s signature, ``/ws/print``'s session) counts the
attempts it refused with an :class:`AttemptLimit` instead: past its ``attempts`` within ``window`` seconds of the first
failure, :meth:`AttemptLimit.wait` says how long the caller waits (``Retry-After``) and the door refuses before it
checks anything; what it accepts is never counted.

A cache that does not answer (Valkey down) raises, as every other use of the cache does: the route fails loudly
rather than turning its limit off.
"""

import logging
import math
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.translation import gettext
from live.errors import OperationError

logger = logging.getLogger(__name__)

#: Where the counts live in the cache, apart from any other key.
KEY_PREFIX = "base.throttle:"
#: Suffix of the key that keeps when an :class:`AttemptLimit`'s window ends (unix seconds).
UNTIL_SUFFIX = ":until"


class RateLimited(OperationError):
    """429 ``base.rate_limited``: the caller went past :func:`allow`'s limit and must wait for the next window."""

    status = 429
    code = "base.rate_limited"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message if message is not None else gettext("Too many requests. Try again in a moment."))


def allow(key: str, *, limit: int, window: int) -> bool:
    """Count one call of ``key``: whether it is within the first ``limit`` calls of its ``window`` seconds."""
    if limit < 1 or window < 1:
        raise ValueError(f"A limit needs limit >= 1 and window >= 1 (got limit={limit}, window={window}).")
    return _count(f"{KEY_PREFIX}{key}", window) <= limit


def _count(cache_key: str, window: int) -> int:
    """Count one call of ``cache_key`` in its window (opened by its first call, ``window`` seconds long)."""
    if cache.add(cache_key, 1, timeout=window):
        return 1
    try:
        count = cache.incr(cache_key)
    except ValueError:
        # The window ended between ``add`` and ``incr`` (the key expired): this call opens the next one.
        cache.add(cache_key, 1, timeout=window)
        count = 1
    if count == 1:
        # Django's Redis ``incr`` checks the key exists, then INCRs: one that expired in between is created again
        # with no TTL, and would count forever. Whoever opens a window gives it its TTL.
        cache.touch(cache_key, timeout=window)
    return count


@dataclass(frozen=True)
class AttemptLimit:
    """At most ``attempts`` refused attempts of a key within ``window`` seconds of its first one.

    The key is ``limit:<name>:<parts…>`` (``limit:callback:<IP>``, ``limit:pin:<hub>:<employee>``…), under
    :data:`KEY_PREFIX`. The door asks :meth:`wait` before it checks the credential and calls :meth:`failed` when it
    refuses it; an accepted attempt is not counted."""

    name: str
    attempts: int
    window: int

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.window < 1:
            raise ValueError(
                f"A limit needs attempts >= 1 and window >= 1 (got attempts={self.attempts}, window={self.window})."
            )

    def key(self, *parts: str) -> str:
        return ":".join(("limit", self.name, *parts))

    def wait(self, *parts: str) -> int:
        """0 while ``parts`` may try; once its failures reached the limit, the seconds until its window ends."""
        cache_key = f"{KEY_PREFIX}{self.key(*parts)}"
        found = cache.get_many([cache_key, cache_key + UNTIL_SUFFIX])
        if found.get(cache_key, 0) < self.attempts:
            return 0
        until = found.get(cache_key + UNTIL_SUFFIX)
        if until is None:
            # The end was evicted: the caller still waits, at most a whole window.
            return self.window
        return max(1, math.ceil(until - time.time()))

    def failed(self, *parts: str) -> None:
        """Count one refused attempt of ``parts``; the one that reaches the limit is logged (never the credential)."""
        key = self.key(*parts)
        cache_key = f"{KEY_PREFIX}{key}"
        count = _count(cache_key, self.window)
        if count == 1:
            cache.set(cache_key + UNTIL_SUFFIX, time.time() + self.window, timeout=self.window)
        if count == self.attempts:
            logger.warning(
                "Attempt limit %r reached by %s: %s refused attempts within %s s; it waits for the window's end.",
                self.name,
                key,
                count,
                self.window,
            )


def client_address(request: HttpRequest) -> str:
    """The caller's address as the proxies in front of the Hub saw it, the one a limit counts.

    Each of ``settings.TRUSTED_PROXY_HOPS`` proxies appends to ``X-Forwarded-For`` the address that connected to it,
    so the caller is the entry that many from the end; whatever comes before it, the client wrote (and Daphne's
    ``--proxy-headers`` puts the first entry in ``REMOTE_ADDR``). With no proxy (local development), or a chain
    shorter than the proxies (a request that did not come through them), the socket's address."""
    hops = settings.TRUSTED_PROXY_HOPS
    chain = [entry.strip() for entry in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if entry.strip()]
    if hops < 1 or len(chain) < hops:
        return request.META.get("REMOTE_ADDR", "")
    return chain[-hops]
