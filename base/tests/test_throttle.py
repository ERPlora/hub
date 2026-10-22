"""``base.throttle``: a fixed-window limit per key on Django's cache (Valkey in AWS), and its 429.

A public route (no session) answers a stranger: ``allow`` counts its calls per key (``(hub, IP)``…) in a window
and says no past the limit; the route then raises ``RateLimited``, the API's envelope with 429.
"""

import json
import time

import pytest
from django.core.cache import cache, caches
from django.test import RequestFactory
from django.utils import translation

from base.throttle import RateLimited, allow, client_address


@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "base-throttle-tests"}
    }
    cache.clear()
    yield
    cache.clear()


def test_the_limit_is_allowed_and_the_next_call_is_not():
    assert [allow("acme:203.0.113.7", limit=3, window=60) for _ in range(4)] == [True, True, True, False]
    assert allow("acme:203.0.113.7", limit=3, window=60) is False


def test_each_key_counts_on_its_own():
    assert [allow("acme:203.0.113.7", limit=1, window=60) for _ in range(2)] == [True, False]
    assert allow("acme:203.0.113.8", limit=1, window=60) is True
    assert allow("bravo:203.0.113.7", limit=1, window=60) is True


def test_the_count_lives_in_its_own_corner_of_the_cache():
    cache.set("acme:203.0.113.7", 99)
    assert allow("acme:203.0.113.7", limit=1, window=60) is True
    assert cache.get("acme:203.0.113.7") == 99


def test_a_new_window_starts_when_the_last_one_ends(monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    assert [allow("acme:203.0.113.7", limit=2, window=60) for _ in range(3)] == [True, True, False]
    monkeypatch.setattr(time, "time", lambda: now + 59)
    assert allow("acme:203.0.113.7", limit=2, window=60) is False
    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert [allow("acme:203.0.113.7", limit=2, window=60) for _ in range(3)] == [True, True, False]


def test_a_window_that_ends_between_the_two_cache_calls_opens_the_next_one(monkeypatch):
    # The count exists when ``add`` looks and is gone when ``incr`` runs (its TTL ran out in between): ``incr`` of a
    # missing key raises ValueError. That call opens the next window, and counts in it.
    backend = caches["default"]
    real_incr = backend.incr
    expired = []

    def incr_after_the_window_ended(key, *args, **kwargs):
        if not expired:
            expired.append(key)
            backend.delete(key)
        return real_incr(key, *args, **kwargs)

    assert allow("acme:203.0.113.7", limit=3, window=60) is True
    monkeypatch.setattr(backend, "incr", incr_after_the_window_ended)
    assert allow("acme:203.0.113.7", limit=3, window=60) is True
    assert expired
    assert [allow("acme:203.0.113.7", limit=3, window=60) for _ in range(3)] == [True, True, False]


def test_a_count_that_incr_recreated_without_a_ttl_still_ends_with_its_window(monkeypatch):
    # Django's Redis ``incr`` checks that the key exists, then INCRs: a key that expires in between comes back as 1
    # with no TTL, and would count (and refuse) forever. A count of 1 out of ``incr`` gets the window again.
    backend = caches["default"]
    real_incr = backend.incr
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)

    def incr_like_redis_after_the_key_expired(key, delta=1, version=None):
        monkeypatch.setattr(backend, "incr", real_incr)
        backend.set(key, delta, timeout=None, version=version)
        return delta

    assert allow("acme:203.0.113.7", limit=2, window=60) is True
    monkeypatch.setattr(backend, "incr", incr_like_redis_after_the_key_expired)
    assert [allow("acme:203.0.113.7", limit=2, window=60) for _ in range(3)] == [True, True, False]
    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert allow("acme:203.0.113.7", limit=2, window=60) is True


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (5, 0), (-1, 60)])
def test_a_limit_or_window_below_one_is_a_programming_error(limit, window):
    with pytest.raises(ValueError):
        allow("acme:203.0.113.7", limit=limit, window=window)


def test_rate_limited_is_the_api_s_429_envelope_in_the_request_s_language():
    from config.api import api

    with translation.override("es"):
        error = RateLimited()
        response = api.on_exception(RequestFactory().get("/api/website/public/catalog"), error)
    assert (error.status, error.code) == (429, "base.rate_limited")
    assert response.status_code == 429
    assert json.loads(response.content) == {
        "error": {"code": "base.rate_limited", "message": "Demasiadas peticiones. Inténtalo de nuevo en un momento."}
    }


def test_rate_limited_takes_a_message_of_its_own():
    assert RateLimited("Slow down.").envelope() == {"error": {"code": "base.rate_limited", "message": "Slow down."}}


# Who the caller is: the address the trusted proxies saw, never one the client wrote


def forwarded(chain: str = "", remote: str = "10.0.1.20"):
    """A request that reached the Hub from ``remote`` with ``X-Forwarded-For: chain`` (none when empty)."""
    headers = {"HTTP_X_FORWARDED_FOR": chain} if chain else {}
    return RequestFactory().get("/api/website/public/site", REMOTE_ADDR=remote, **headers)


def test_behind_one_proxy_the_caller_is_the_address_it_appended(settings):
    # The ALB appends the address that connected to it: what comes before it, the client wrote. Daphne's
    # --proxy-headers takes the first entry for REMOTE_ADDR, so the socket's address is no better.
    settings.TRUSTED_PROXY_HOPS = 1
    assert client_address(forwarded("203.0.113.7")) == "203.0.113.7"
    assert client_address(forwarded("198.51.100.1, 203.0.113.7")) == "203.0.113.7"
    assert client_address(forwarded("1.1.1.1, 2.2.2.2,203.0.113.7 ")) == "203.0.113.7"


def test_behind_two_proxies_the_caller_is_the_second_from_the_end(settings):
    settings.TRUSTED_PROXY_HOPS = 2
    assert client_address(forwarded("198.51.100.1, 203.0.113.7, 10.0.0.5")) == "203.0.113.7"


def test_a_chain_shorter_than_the_proxies_is_the_socket(settings):
    # Nothing the proxies wrote: the request did not come through them (a health check, a call inside the VPC).
    settings.TRUSTED_PROXY_HOPS = 2
    assert client_address(forwarded("203.0.113.7")) == "10.0.1.20"
    assert client_address(forwarded()) == "10.0.1.20"


def test_without_proxies_the_header_is_ignored(settings):
    # Local development: nothing in front of runserver, so whatever the header says, the client wrote.
    settings.TRUSTED_PROXY_HOPS = 0
    assert client_address(forwarded("198.51.100.1, 203.0.113.7")) == "10.0.1.20"


def test_a_spoofed_entry_never_changes_the_callers_count(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    for fake in ("198.51.100.1", "198.51.100.2", "198.51.100.3"):
        assert allow(f"acme:{client_address(forwarded(f'{fake}, 203.0.113.7'))}", limit=2, window=60) is (
            fake != "198.51.100.3"
        )
