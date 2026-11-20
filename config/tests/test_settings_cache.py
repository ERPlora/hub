"""The cache: Valkey when set, with keys of its own for pre, and the process's memory in the test run."""

import os
import subprocess
import sys

import pytest
from django.conf import settings
from django.core.cache import CacheHandler
from django.core.exceptions import ImproperlyConfigured

from config.tests.settings_env import BASE_DIR, DEVELOPMENT_ENV, PRODUCTION_ENV


def test_the_cache_is_valkey_when_set(load_settings):
    # Without it, the disk of the control database: base/tests/test_cache_between_processes.py.
    loaded = load_settings(**PRODUCTION_ENV, VALKEY_URL="rediss://cache.example:6379")
    # A prefix per project on the shared Valkey, a TTL on every key (never TIMEOUT=None) and 2 s
    # socket timeouts, as saas-next's.
    assert loaded["CACHES"] == {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "rediss://cache.example:6379",
            "KEY_PREFIX": "hub",
            "TIMEOUT": 300,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
    }


# ── The environment: prod or pre, the team's pre-production on the same Valkey ──

VALKEY_ENV = {"VALKEY_URL": "rediss://cache.example:6379"}


def test_the_environment_defaults_to_prod_and_keeps_the_hub_cache_prefix(load_settings):
    # A task without ERPLORA_ENVIRONMENT is prod's, with the cache keys it has always had.
    loaded = load_settings(**PRODUCTION_ENV, **VALKEY_ENV)
    assert loaded["ERPLORA_ENVIRONMENT"] == "prod"
    assert loaded["CACHES"]["default"]["KEY_PREFIX"] == "hub"
    loaded = load_settings(**PRODUCTION_ENV, **VALKEY_ENV, ERPLORA_ENVIRONMENT="prod")
    assert loaded["CACHES"]["default"]["KEY_PREFIX"] == "hub"
    assert load_settings(**DEVELOPMENT_ENV)["ERPLORA_ENVIRONMENT"] == "prod"


def test_pre_prefixes_every_cache_key(load_settings):
    # pre and prod share one Valkey: with prod's prefix, pre would read and overwrite its keys.
    loaded = load_settings(**PRODUCTION_ENV, **VALKEY_ENV, ERPLORA_ENVIRONMENT="pre")
    assert loaded["ERPLORA_ENVIRONMENT"] == "pre"
    assert loaded["CACHES"]["default"]["KEY_PREFIX"] == "pre-hub"
    cache = CacheHandler(loaded["CACHES"])["default"]
    assert cache.make_key("throttle") == "pre-hub:1:throttle"


@pytest.mark.parametrize("environment", ["dev", "PRE", "production", " pre", ""])
def test_an_unknown_environment_refuses_to_start(load_settings, environment):
    with pytest.raises(ImproperlyConfigured, match="ERPLORA_ENVIRONMENT"):
        load_settings(**PRODUCTION_ENV, ERPLORA_ENVIRONMENT=environment)


@pytest.mark.parametrize("env", [DEVELOPMENT_ENV, PRODUCTION_ENV])
def test_a_valkey_that_hangs_fails_the_cache_call_within_two_seconds(
    load_settings, env
):
    # Without them redis-py waits forever: a hung Valkey would hang the request. Django passes the
    # OPTIONS of RedisCache to the client's connection pool.
    loaded = load_settings(**env, VALKEY_URL="redis://localhost:6379/0")
    client = CacheHandler(loaded["CACHES"])["default"]._cache.get_client()
    kwargs = client.connection_pool.connection_kwargs
    assert (kwargs["socket_connect_timeout"], kwargs["socket_timeout"]) == (2, 2)


def test_without_valkey_the_local_cache_has_no_socket_to_time_out(load_settings):
    for env in (DEVELOPMENT_ENV, PRODUCTION_ENV):
        assert "OPTIONS" not in load_settings(**env)["CACHES"]["default"]


def test_the_valkey_cache_client_builds_so_its_library_is_installed(load_settings):
    # Production sets VALKEY_URL: without the redis library, the first cache use raises
    # ModuleNotFoundError. Building the client neither connects nor needs a server.
    loaded = load_settings(**PRODUCTION_ENV, VALKEY_URL="redis://localhost:6379/0")
    cache = CacheHandler(loaded["CACHES"])["default"]
    client = cache._cache.get_client()
    assert client.connection_pool.connection_kwargs["host"] == "localhost"
    assert client.connection_pool.connection_kwargs["db"] == 0


def test_the_test_run_keeps_its_cache_in_memory_even_with_a_valkey_in_the_environment():
    # conftest.py empties the cache around every test (base.throttle's attempt counts): pointed at a real Valkey, that
    # would wipe whatever it holds. The test settings keep the process's memory whatever VALKEY_URL says, refusing what
    # the Valkey cluster of AWS refuses (base/cache.py, hub#440): a call on keys of different slots fails every test.
    env = {**os.environ, "VALKEY_URL": "rediss://valkey.invalid:6379/0", "DJANGO_SETTINGS_MODULE": "config.settings_pytest"}
    result = subprocess.run(
        [sys.executable, "-c", "from django.conf import settings; print(settings.CACHES['default']['BACKEND'])"],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "base.cache.ClusterLocMemCache"
    assert settings.CACHES["default"]["BACKEND"] == "base.cache.ClusterLocMemCache"
