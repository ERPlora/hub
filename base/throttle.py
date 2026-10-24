"""A fixed-window limit per key on Django's cache (Valkey in AWS, the process's memory locally), and its 429.

A route that answers without a session (a hub's public website) counts its callers with :func:`allow`, by a key of
its own (``"<app>:<hub slug>:<IP>"``, the IP by :func:`client_address`), and raises :class:`RateLimited` when it says
no: the API's error envelope, 429 ``base.rate_limited``, in the request's language. The count lives under
:data:`KEY_PREFIX` for ``window`` seconds from the window's first call; the next call after that opens a new window.

A door that checks a credential (the login's callback, ``/internal``'s signature, ``/ws/print``'s session) counts the
attempts it refused with an :class:`AttemptLimit` instead: past its ``attempts`` within ``window`` seconds of the first
failure, the next refused attempt of that caller (:func:`client_key`) is answered 429 (:meth:`AttemptLimit.wait`, the
``Retry-After``) until the window ends. The door checks the credential first: what it accepts is never counted nor
refused, so a valid caller behind the same address (a restaurant's other devices) is never locked out.

A cache that does not answer (Valkey down) makes :func:`allow` raise, as every other use of the cache does: the public
route fails loudly rather than turning its limit off. An :class:`AttemptLimit` steps aside instead, with an error in
the log: the doors it guards (the login, printing, the SaaS's calls) must not stop with Valkey, as ``/readyz`` does
not, and the credential each one checks holds on its own.
"""

import ipaddress
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
    :data:`KEY_PREFIX`. The door checks the credential first; when it refuses it, :meth:`wait` says whether the caller
    already waits (its 429) and otherwise :meth:`failed` counts it. An accepted attempt is neither counted nor refused."""

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
        """0 while ``parts`` may try; once its failures reached the limit, the seconds until its window ends.

        0 too when the cache does not answer (logged): the door goes on to check the credential."""
        cache_key = f"{KEY_PREFIX}{self.key(*parts)}"
        try:
            found = cache.get_many([cache_key, cache_key + UNTIL_SUFFIX])
        except Exception:
            logger.exception("Attempt limit %r is off for this call: the cache did not answer.", self.name)
            return 0
        if found.get(cache_key, 0) < self.attempts:
            return 0
        until = found.get(cache_key + UNTIL_SUFFIX)
        if until is None:
            # The end was evicted: the caller still waits, at most a whole window.
            return self.window
        return max(1, math.ceil(until - time.time()))

    def failed(self, *parts: str) -> None:
        """Count one refused attempt of ``parts``; the one that reaches the limit is logged (never the credential).

        Not counted when the cache does not answer (logged)."""
        key = self.key(*parts)
        cache_key = f"{KEY_PREFIX}{key}"
        try:
            count = _count(cache_key, self.window)
            if count == 1:
                cache.set(cache_key + UNTIL_SUFFIX, time.time() + self.window, timeout=self.window)
        except Exception:
            logger.exception("Attempt limit %r did not count a refused attempt: the cache did not answer.", self.name)
            return
        if count == self.attempts:
            logger.warning(
                "Attempt limit %r reached by %s: %s refused attempts within %s s; it waits for the window's end.",
                self.name,
                key,
                count,
                self.window,
            )


    def clear(self, *parts: str) -> None:
        """Forget the refused attempts of ``parts`` (a right PIN starts its person's count again). A cache that does
        not answer leaves them (logged): they end with their window."""
        cache_key = f"{KEY_PREFIX}{self.key(*parts)}"
        try:
            cache.delete_many([cache_key, cache_key + UNTIL_SUFFIX])
        except Exception:
            logger.exception("Attempt limit %r did not forget %s: the cache did not answer.", self.name, self.key(*parts))


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


def client_key(request: HttpRequest) -> str:
    """The caller an :class:`AttemptLimit` counts: :func:`client_address`, or the /64 of an IPv6 one.

    One subscriber holds a whole IPv6 /64 and picks any address inside it, so counting each address would let it try
    without end. An IPv4 address inside IPv6 (``::ffff:a.b.c.d``) is that IPv4 address; what is not an address (none,
    a test's) is kept as it is."""
    address = client_address(request)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ipaddress.IPv6Network((int(ip) >> 64 << 64, 64)))
