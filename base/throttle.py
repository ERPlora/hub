"""A fixed-window limit per key on Django's cache (Valkey in AWS, the process's memory locally), and its 429.

A route that answers without a session (a hub's public website) counts its callers with :func:`allow`, by a key of
its own (``"<app>:<hub slug>:<IP>"``, the IP by :func:`client_address`), and raises :class:`RateLimited` when it says
no: the API's error envelope, 429 ``base.rate_limited``, in the request's language. The count lives under
:data:`KEY_PREFIX` for ``window`` seconds from the window's first call; the next call after that opens a new window.

A cache that does not answer (Valkey down) raises, as every other use of the cache does: the route fails loudly
rather than turning its limit off.
"""

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.translation import gettext
from live.errors import OperationError

#: Where the counts live in the cache, apart from any other key.
KEY_PREFIX = "base.throttle:"


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
    cache_key = f"{KEY_PREFIX}{key}"
    if cache.add(cache_key, 1, timeout=window):
        return True
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
    return count <= limit


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
