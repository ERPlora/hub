"""``base.throttle``: a fixed-window limit per key on Django's cache (Valkey in AWS), and its 429.

A public route (no session) answers a stranger: ``allow`` counts its calls per key (``(hub, IP)``…) in a window
and says no past the limit; the route then raises ``RateLimited``, the API's envelope with 429.
"""

import json
import logging
import time

import pytest
from django.core.cache import cache, caches
from django.test import RequestFactory
from django.utils import translation

from base.throttle import KEY_PREFIX, AttemptLimit, RateLimited, allow, client_address


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


# Failed attempts: a door counts what it refused, and past the limit the caller waits for the window's end


CALLBACK = AttemptLimit("callback", attempts=3, window=300)


def test_a_key_tries_freely_until_its_failures_reach_the_limit():
    for _ in range(2):
        CALLBACK.failed("203.0.113.7")
    assert CALLBACK.wait("203.0.113.7") == 0
    CALLBACK.failed("203.0.113.7")
    assert CALLBACK.wait("203.0.113.7") == 300


def test_the_wait_is_what_is_left_of_the_window_its_first_failure_opened(monkeypatch):
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now)
    CALLBACK.failed("203.0.113.7")
    monkeypatch.setattr(time, "time", lambda: now + 100)
    CALLBACK.failed("203.0.113.7")
    CALLBACK.failed("203.0.113.7")
    assert CALLBACK.wait("203.0.113.7") == 200
    monkeypatch.setattr(time, "time", lambda: now + 299.5)
    assert CALLBACK.wait("203.0.113.7") == 1
    monkeypatch.setattr(time, "time", lambda: now + 301)
    assert CALLBACK.wait("203.0.113.7") == 0
    CALLBACK.failed("203.0.113.7")
    assert CALLBACK.wait("203.0.113.7") == 0, "a new window starts its count again"


def test_each_key_and_each_limit_count_on_their_own():
    for _ in range(3):
        CALLBACK.failed("203.0.113.7")
    assert CALLBACK.wait("203.0.113.8") == 0
    assert AttemptLimit("internal", attempts=3, window=300).wait("203.0.113.7") == 0
    assert CALLBACK.wait("203.0.113.7") == 300


def test_the_parts_make_a_namespaced_key_in_the_throttle_s_corner_of_the_cache():
    limit = AttemptLimit("pin", attempts=1, window=60)
    assert limit.key("acme", "42") == "limit:pin:acme:42"
    limit.failed("acme", "42")
    assert cache.get(f"{KEY_PREFIX}limit:pin:acme:42") == 1
    assert cache.get("limit:pin:acme:42") is None


def test_a_count_whose_window_end_was_lost_waits_the_whole_window():
    # The end of the window is a key of its own; a cache that dropped it (evicted) still makes the caller wait, at most
    # a whole window, never zero.
    for _ in range(3):
        CALLBACK.failed("203.0.113.7")
    cache.delete(f"{KEY_PREFIX}{CALLBACK.key('203.0.113.7')}:until")
    assert CALLBACK.wait("203.0.113.7") == 300


def test_a_window_end_this_clock_sees_as_past_still_waits_a_second():
    # Valkey keeps the count by its own clock and each task reads the end by its own: a task whose clock runs ahead
    # sees the end already past while the count is alive. It still refuses (1 s), never 0 or a negative Retry-After.
    for _ in range(3):
        CALLBACK.failed("203.0.113.7")
    cache.set(f"{KEY_PREFIX}{CALLBACK.key('203.0.113.7')}:until", time.time() - 10, timeout=300)
    assert CALLBACK.wait("203.0.113.7") == 1


def test_the_failure_that_reaches_the_limit_is_logged_once(caplog):
    with caplog.at_level(logging.WARNING, logger="base.throttle"):
        for _ in range(5):
            CALLBACK.failed("203.0.113.7")
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "callback" in record.getMessage() and "203.0.113.7" in record.getMessage()


def cache_away(*args, **kwargs):
    raise ConnectionError("Valkey is not answering")


def test_with_the_cache_away_the_door_still_checks_and_the_outage_is_logged(monkeypatch, caplog):
    # Login, printing and the SaaS's calls must not stop with Valkey (as /readyz does not): the credential each door
    # checks holds on its own, so the limit steps aside, loudly, instead of refusing everyone or failing the request.
    backend = caches["default"]
    for method in ("get_many", "add", "incr", "set", "touch"):
        monkeypatch.setattr(backend, method, cache_away)
    with caplog.at_level(logging.ERROR, logger="base.throttle"):
        assert CALLBACK.wait("203.0.113.7") == 0
        CALLBACK.failed("203.0.113.7")
    assert [record.levelno for record in caplog.records] == [logging.ERROR, logging.ERROR]
    assert all("callback" in record.getMessage() and record.exc_info for record in caplog.records)


def test_a_public_count_still_fails_loudly_with_the_cache_away(monkeypatch):
    # ``allow`` (the public website) keeps its rule: no cache, no answer.
    monkeypatch.setattr(caches["default"], "add", cache_away)
    with pytest.raises(ConnectionError):
        allow("acme:203.0.113.7", limit=3, window=60)


@pytest.mark.parametrize(("attempts", "window"), [(0, 60), (5, 0), (-1, 60)])
def test_an_attempt_limit_below_one_is_a_programming_error(attempts, window):
    with pytest.raises(ValueError):
        AttemptLimit("callback", attempts=attempts, window=window)
