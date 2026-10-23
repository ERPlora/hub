"""hub-next settings: env through decouple, Postgres with a pool, CSP per DEBUG, WhiteNoise, LIVE."""

import hashlib
import os
import re
import runpy
import secrets
import subprocess
import sys
from pathlib import Path

import decouple
import pytest
from django.conf import settings
from django.core.cache import CacheHandler
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import mailers
from django.test import RequestFactory, override_settings
from live.csp import base_policy, debug_policy
from live.slugs import is_reserved_hub_slug

SETTINGS_FILE = Path(__file__).resolve().parents[1] / "settings.py"
BASE_DIR = SETTINGS_FILE.parents[1]
ENV_KEYS = (
    "DEBUG",
    "SECRET_KEY",
    "ALLOWED_HOSTS",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "SAAS_URL",
    "SAAS_INTERNAL_URL",
    "INTERNAL_SHARED_SECRET",
    "DB_SSLMODE",
    "DB_SSLROOTCERT",
    "DB_APPLICATION_NAME",
    "PGBOUNCER_HOST",
    "PGBOUNCER_PORT",
    "DB_CONNECT_TIMEOUT",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "VALKEY_URL",
    "LOG_LEVEL",
    "SES_REGION",
    "EMAIL_BACKEND",
    "EMAIL_HOST",
    "EMAIL_PORT",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
    "EMAIL_USE_TLS",
    "DEFAULT_FROM_EMAIL",
    "SHARED_DB_USER",
    "SHARED_DB_PASSWORD",
    "SHARED_DB_NAME",
    "APP_VERSION",
    "APP_RELEASED_AT",
    "WORKBOOK_TRANSLATION_MODEL",
    "TEST_DB_NAME",
    "ERPLORA_ENVIRONMENT",
    "HUB_BASE_DOMAIN",
    "FISCAL_CERTIFICATE_KEY",
    "FLOW_SECRETS_KEY",
    "VITE_DEV_PORT",
    "AWS_STORAGE_BUCKET_NAME",
    "AWS_REGION",
    "MEDIA_ROOT",
)
# Local development opts in with DEBUG=True (the .env of a checkout); nothing else turns it on.
DEVELOPMENT_ENV = {"DEBUG": "True"}
PRODUCTION_ENV = {
    "DEBUG": "False",
    "SECRET_KEY": "from-the-environment",
    "SAAS_URL": "https://erplora.com",
    "INTERNAL_SHARED_SECRET": "shared-with-the-saas",
}


@pytest.fixture
def load_settings(monkeypatch, tmp_path):
    """Run settings.py again with only the given environment (no .env file) and return its globals."""

    def load(**env: str) -> dict:
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(
            decouple, "config", decouple.AutoConfig(search_path=str(tmp_path))
        )
        return runpy.run_path(str(SETTINGS_FILE))

    return load


def test_live_precedes_daphne_so_its_runserver_wins():
    installed = settings.INSTALLED_APPS
    assert installed.index("live") < installed.index("daphne")
    assert {"ninja", "base", "apps.demo"} <= set(installed)


def test_base_precedes_the_admin_so_its_admin_templates_win():
    # base/templates/admin/base_site.html adds the chosen hub's banner (round 13, PLAN §18.1).
    installed = settings.INSTALLED_APPS
    assert installed.index("base") < installed.index("django.contrib.admin")


def test_the_platform_host_is_hubs_and_no_customer_can_take_it():
    # hubs.erplora.com (locally hubs.localhost:8000) is only the Hub admin for the staff (PLAN §18.1);
    # `hub` stays reserved but is not the platform host.
    assert settings.PLATFORM_HOST_LABEL == "hubs"
    assert is_reserved_hub_slug(settings.PLATFORM_HOST_LABEL)


def test_defaults_are_the_local_compose_database_with_a_pool(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    db = loaded["DATABASES"]["default"]
    assert db["ENGINE"] == "django.db.backends.postgresql"
    assert (db["NAME"], db["USER"], db["PASSWORD"], db["HOST"], db["PORT"]) == (
        "hub",
        "hub",
        "hub",
        "127.0.0.1",
        5432,
    )
    assert db["OPTIONS"]["pool"] == {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5}
    # Its own test database, so it never drops the one the packages/live suite is using.
    assert db["TEST"]["NAME"] == "test_hub_next"


def test_database_comes_from_the_environment(load_settings):
    loaded = load_settings(
        **DEVELOPMENT_ENV, DB_NAME="other", DB_HOST="db.internal", DB_PORT="6543"
    )
    db = loaded["DATABASES"]["default"]
    assert (db["NAME"], db["HOST"], db["PORT"]) == ("other", "db.internal", 6543)


def with_saas_origin(policy: dict, saas_origin: str) -> dict:
    """``policy`` with the SaaS's origin where the Hub's page reaches it: ``form-action`` (the logout's
    redirect leaves for it), ``img-src`` and ``media-src`` (the WhatsApp attachments it serves)."""
    return {
        **policy,
        "form-action": [*policy["form-action"], saas_origin],
        "img-src": [*policy["img-src"], saas_origin],
        "media-src": ["'self'", saas_origin],
    }


def test_debug_defaults_to_false_so_a_missing_variable_never_turns_it_on(load_settings):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DEBUG"}
    loaded = load_settings(**env)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == with_saas_origin(
        base_policy(), "https://erplora.com"
    )
    assert loaded["LIVE"]["spa"]["dev_server"] is None


def test_without_debug_nor_a_secret_key_the_settings_refuse_to_start(load_settings):
    # No DEBUG means production: the known local key is never a fallback.
    with pytest.raises(decouple.UndefinedValueError, match="SECRET_KEY"):
        load_settings()


def test_development_uses_the_debug_csp_and_vite(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["DEBUG"] is True
    assert loaded["SECURE_CSP"] == with_saas_origin(
        debug_policy(), "http://localhost:8001"
    )
    assert loaded["LIVE"]["spa"]["dev_server"] == "http://localhost:5173"
    assert loaded["ALLOWED_HOSTS"] == [".localhost", "127.0.0.1", "localhost"]


def test_the_vite_port_comes_from_the_environment(load_settings):
    # A second checkout runs beside another session's runserver (its Vite owns 5173): the e2e of a
    # branch sets VITE_DEV_PORT for Django and for vite.config.ts alike.
    loaded = load_settings(**DEVELOPMENT_ENV, VITE_DEV_PORT="5183")
    assert loaded["LIVE"]["spa"]["dev_server"] == "http://localhost:5183"
    assert loaded["SECURE_CSP"] == with_saas_origin(
        debug_policy("http://localhost:5183"), "http://localhost:8001"
    )


def test_a_vite_port_that_is_no_port_refuses_to_start(load_settings):
    with pytest.raises(ImproperlyConfigured, match="VITE_DEV_PORT"):
        load_settings(**DEVELOPMENT_ENV, VITE_DEV_PORT="70000")


@pytest.mark.parametrize("source", ["environment", "dotenv-only"])
def test_runserver_starts_vite_on_the_port_django_read(load_settings, tmp_path, source):
    """`manage.py runserver` starts Vite with LIVE["vite"] and the process environment (packages/live),
    and vite.config.ts reads VITE_DEV_PORT from that environment only, while Django reads it from the
    environment or from .env. The command carries the port Django chose, whatever its source: with the
    variable only in .env, Django's page pointed at :5203 while its Vite listened on :5173 (or died on
    the Vite already there), and the page never loaded."""
    if source == "environment":
        loaded = load_settings(**DEVELOPMENT_ENV, VITE_DEV_PORT="5203")
    else:
        (tmp_path / ".env").write_text("VITE_DEV_PORT=5203\n")
        loaded = load_settings(**DEVELOPMENT_ENV)

    assert loaded["LIVE"]["spa"]["dev_server"] == "http://localhost:5203"
    assert loaded["LIVE"]["vite"]["command"] == ["env", "VITE_DEV_PORT=5203", "pnpm", "run", "dev"]


def test_production_uses_the_base_csp_and_no_dev_server(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == with_saas_origin(
        base_policy(), "https://erplora.com"
    )
    assert loaded["LIVE"]["spa"]["dev_server"] is None
    assert loaded["SECRET_KEY"] == "from-the-environment"


@pytest.mark.parametrize(
    "saas_url",
    ["https://erplora.com", "https://erplora.com/", "https://erplora.com/some/path"],
)
def test_form_action_lets_the_logout_go_on_to_the_saas_s_origin_only(
    load_settings, saas_url
):
    # The SPA's logout POSTs a form to /auth/logout, which answers 302 to the SaaS: form-action filters
    # the whole redirect chain, so 'self' alone left the page where it was (Hub session closed).
    loaded = load_settings(**{**PRODUCTION_ENV, "SAAS_URL": saas_url})
    assert loaded["SECURE_CSP"]["form-action"] == ["'self'", "https://erplora.com"]


@pytest.mark.parametrize(
    ("env", "policy", "saas_origin"),
    [
        (
            {**PRODUCTION_ENV, "SAAS_URL": "https://erplora.com/some/path"},
            base_policy(),
            "https://erplora.com",
        ),
        (DEVELOPMENT_ENV, debug_policy(), "http://localhost:8001"),
    ],
    ids=["production", "development"],
)
def test_the_inbox_shows_photos_and_voice_notes_from_the_saas_s_origin_only(
    load_settings, env, policy, saas_origin
):
    # The SaaS serves a WhatsApp conversation's attachments (/whatsapp/media/<id>): the thread shows the photo
    # and plays the voice note from its origin, and from nowhere else (no `*`, `https:` nor Meta's CDN).
    # Nothing else widens: connect-src keeps the Tauri bridge (ipc:) as live.csp gives it.
    csp = load_settings(**env)["SECURE_CSP"]
    assert csp["img-src"] == [*policy["img-src"], saas_origin]
    assert csp["media-src"] == ["'self'", saas_origin]
    for unchanged in ("default-src", "script-src", "connect-src"):
        assert csp[unchanged] == policy[unchanged]


@pytest.mark.parametrize("env", [PRODUCTION_ENV, DEVELOPMENT_ENV], ids=["production", "development"])
def test_the_gate_pages_take_their_stylesheet_and_logo_from_self(load_settings, env):
    # A hub being prepared, gone or suspended answers a page rendered without the request (no nonce): it wears
    # base's static stylesheet and logo (/static/base/), which only 'self' lets in.
    csp = load_settings(**env)["SECURE_CSP"]
    assert "'self'" in csp["style-src"]
    assert "'self'" in csp["img-src"]


@pytest.mark.parametrize(
    "missing", ["SECRET_KEY", "SAAS_URL", "INTERNAL_SHARED_SECRET"]
)
def test_production_without_a_secret_or_the_saas_refuses_to_start(
    load_settings, missing
):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != missing}
    with pytest.raises(decouple.UndefinedValueError, match=missing):
        load_settings(**env)


def test_the_saas_defaults_to_the_local_one_in_development(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    # The SaaS is erplora.com (localhost:8001 locally); hubs.localhost is the Hub admin's host.
    assert loaded["SAAS_URL"] == "http://localhost:8001"
    # The same local default as saas-next's, or the local redeem is rejected as unsigned.
    assert loaded["INTERNAL_SHARED_SECRET"] == "local-internal-shared-secret"


def test_the_saas_and_its_shared_secret_come_from_the_environment(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert (loaded["SAAS_URL"], loaded["INTERNAL_SHARED_SECRET"]) == (
        "https://erplora.com",
        "shared-with-the-saas",
    )


def test_the_automations_secrets_key_comes_from_the_environment(load_settings):
    """The key that seals the secrets the automations use (FLOW-F26); without it the Hub starts and refuses,
    visibly, to keep or use a secret."""
    assert load_settings(**PRODUCTION_ENV)["FLOW_SECRETS_KEY"] == ""
    key = "Hh3cG0mN2r1n6Xl2X3oYgq1xk3s0b4b8XG0bN3J3yPQ="
    assert load_settings(**PRODUCTION_ENV, FLOW_SECRETS_KEY=key)["FLOW_SECRETS_KEY"] == key


def test_the_fiscal_certificate_key_comes_from_the_environment(load_settings):
    """The key that seals a business's own certificate in its hub database (VeriFactu); without it the Hub
    starts and refuses, visibly, to keep a certificate."""
    assert load_settings(**PRODUCTION_ENV)["FISCAL_CERTIFICATE_KEY"] == ""
    key = "Hh3cG0mN2r1n6Xl2X3oYgq1xk3s0b4b8XG0bN3J3yPQ="
    assert (
        load_settings(**PRODUCTION_ENV, FISCAL_CERTIFICATE_KEY=key)["FISCAL_CERTIFICATE_KEY"]
        == key
    )


def test_the_internal_saas_url_defaults_to_the_public_one(load_settings):
    # Locally (and wherever the SaaS has no private name) /internal goes where the browser goes.
    assert (
        load_settings(**DEVELOPMENT_ENV)["SAAS_INTERNAL_URL"] == "http://localhost:8001"
    )
    assert (
        load_settings(**DEVELOPMENT_ENV, SAAS_URL="http://saas.test")[
            "SAAS_INTERNAL_URL"
        ]
        == "http://saas.test"
    )
    assert load_settings(**PRODUCTION_ENV)["SAAS_INTERNAL_URL"] == "https://erplora.com"


def test_the_internal_saas_url_comes_from_the_environment(load_settings):
    # Production: the ALB answers 404 to /internal/*, so the Hub calls the SaaS by its Cloud Map name.
    loaded = load_settings(
        **PRODUCTION_ENV, SAAS_INTERNAL_URL="http://saas.erplora.internal:8000"
    )
    assert (loaded["SAAS_URL"], loaded["SAAS_INTERNAL_URL"]) == (
        "https://erplora.com",
        "http://saas.erplora.internal:8000",
    )


def test_a_burst_of_pooled_connections_is_given_back_within_minutes(load_settings):
    # psycopg_pool closes one connection above min_size per max_idle, 600 s by default: a scanner
    # burst on *.erplora.com (60 requests/s, 2026-10-18) left the idle hub web holding its 8 control
    # connections for over an hour. With 60 s it is back to one within 7 minutes; that one stays
    # open for the next request (PLAN-DB «Conexiones», round 2026-10-18).
    pool = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]["pool"]
    assert (pool["min_size"], pool["max_size"], pool["max_idle"]) == (1, 8, 60)


@pytest.mark.django_db
def test_the_running_pool_closes_idle_connections_after_60_seconds():
    # Django hands OPTIONS["pool"] to psycopg_pool as is: the pool this process opened has it.
    from django.db import connection

    connection.ensure_connection()
    assert (connection.pool.min_size, connection.pool.max_idle) == (1, 60)


def test_database_tls_and_application_name_only_when_set(load_settings):
    options = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]
    assert options == {
        "pool": {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5},
        "connect_timeout": 5,
    }
    loaded = load_settings(
        **PRODUCTION_ENV,
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
        DB_APPLICATION_NAME="worker",
    )
    assert loaded["DATABASES"]["default"]["OPTIONS"] == {
        "pool": {"min_size": 1, "max_size": 8, "max_idle": 60, "timeout": 5},
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ssl/certs/rds-global-bundle.pem",
        "application_name": "worker",
    }


def test_a_dead_database_fails_within_db_connect_timeout_seconds(load_settings):
    # psycopg waits 30 s for a connection from the pool and 130 s per connection attempt, so a dead
    # database made /readyz answer 503 after its probes had given up. Both waits are
    # DB_CONNECT_TIMEOUT seconds, 5 by default.
    options = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]
    assert (options["connect_timeout"], options["pool"]["timeout"]) == (5, 5)
    options = load_settings(**DEVELOPMENT_ENV, DB_CONNECT_TIMEOUT="2")["DATABASES"][
        "default"
    ]["OPTIONS"]
    assert (options["connect_timeout"], options["pool"]["timeout"]) == (2, 2)


def test_production_cookies_are_secure_and_hsts_is_on_for_the_hub_host_only(
    load_settings,
):
    loaded = load_settings(**PRODUCTION_ENV)
    assert (loaded["SESSION_COOKIE_SECURE"], loaded["CSRF_COOKIE_SECURE"]) == (
        True,
        True,
    )
    assert loaded["SECURE_HSTS_SECONDS"] == 31536000
    # The domain-wide policy (subdomains, preload list) is the apex's, erplora.com: opt-in here.
    assert (
        loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"],
        loaded["SECURE_HSTS_PRELOAD"],
    ) == (False, False)


def test_development_keeps_plain_cookies_and_no_hsts(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert (loaded["SESSION_COOKIE_SECURE"], loaded["CSRF_COOKIE_SECURE"]) == (
        False,
        False,
    )
    assert loaded["SECURE_HSTS_SECONDS"] == 0


def test_hsts_comes_from_the_environment(load_settings):
    loaded = load_settings(
        **PRODUCTION_ENV,
        SECURE_HSTS_SECONDS="60",
        SECURE_HSTS_INCLUDE_SUBDOMAINS="True",
        SECURE_HSTS_PRELOAD="True",
    )
    assert (
        loaded["SECURE_HSTS_SECONDS"],
        loaded["SECURE_HSTS_INCLUDE_SUBDOMAINS"],
        loaded["SECURE_HSTS_PRELOAD"],
    ) == (
        60,
        True,
        True,
    )


@pytest.mark.parametrize("env", [PRODUCTION_ENV, DEVELOPMENT_ENV], ids=["production", "development"])
def test_the_hub_s_pages_keep_the_windows_they_open_so_a_sign_in_window_can_answer(load_settings, env):
    # Meta's window to connect a WhatsApp number (WHATSAPP_INBOX-F01/F02, Embedded Signup) and the SaaS's return
    # page post back to the page that opened them: Django's default `same-origin` leaves them no opener. Nothing
    # looser than allow-popups: `unsafe-none` would also let a page of another origin that opens the Hub keep it.
    assert load_settings(**env)["SECURE_CROSS_ORIGIN_OPENER_POLICY"] == "same-origin-allow-popups"


def test_production_trusts_the_alb_as_one_proxy_and_development_none(load_settings):
    # The ALB appends the caller's address to X-Forwarded-For (base.throttle.client_address); runserver has nothing
    # in front of it.
    assert load_settings(**PRODUCTION_ENV)["TRUSTED_PROXY_HOPS"] == 1
    assert load_settings(**DEVELOPMENT_ENV)["TRUSTED_PROXY_HOPS"] == 0
    assert load_settings(**PRODUCTION_ENV, TRUSTED_PROXY_HOPS="2")["TRUSTED_PROXY_HOPS"] == 2


def test_a_negative_number_of_proxies_refuses_to_start(load_settings):
    with pytest.raises(ImproperlyConfigured, match="TRUSTED_PROXY_HOPS"):
        load_settings(**PRODUCTION_ENV, TRUSTED_PROXY_HOPS="-1")


def test_a_request_the_alb_forwarded_over_https_is_secure():
    # The ALB terminates TLS and sets X-Forwarded-Proto (daphne --proxy-headers reads it too).
    factory = RequestFactory()
    assert factory.get("/", HTTP_X_FORWARDED_PROTO="https").is_secure()
    assert not factory.get("/", HTTP_X_FORWARDED_PROTO="http").is_secure()
    # The SaaS's calls over the private name (plain HTTP, no ALB) are not.
    assert not factory.get("/").is_secure()


def test_the_cache_is_valkey_when_set_else_local_memory(load_settings):
    assert load_settings(**DEVELOPMENT_ENV)["CACHES"] == {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
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


# ── The environment: prod or pre, the team's pre-production on the same Valkey (plan 2026-10-14) ──

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


def test_hub_base_domain_comes_from_the_environment(load_settings):
    # Production's hubs live under erplora.com, locally under localhost (a.localhost:8000).
    assert load_settings(**PRODUCTION_ENV)["HUB_BASE_DOMAIN"] == "erplora.com"
    assert load_settings(**DEVELOPMENT_ENV)["HUB_BASE_DOMAIN"] == "localhost"
    # pre: <slug>.pre.erplora.com and hubs.pre.erplora.com; written in any case, with dots around.
    loaded = load_settings(**PRODUCTION_ENV, HUB_BASE_DOMAIN=".Pre.Erplora.com.")
    assert loaded["HUB_BASE_DOMAIN"] == "pre.erplora.com"
    # Empty: no base domain, the hub is the Host's first label wherever it is (before 2026-10-14).
    assert load_settings(**PRODUCTION_ENV, HUB_BASE_DOMAIN="")["HUB_BASE_DOMAIN"] == ""


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


def test_without_valkey_the_local_memory_cache_has_no_socket_to_time_out(load_settings):
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


def test_logs_go_to_the_console_at_the_level_of_the_environment(load_settings):
    logging = load_settings(**PRODUCTION_ENV)["LOGGING"]
    assert logging["handlers"]["console"]["class"] == "logging.StreamHandler"
    assert logging["root"] == {"handlers": ["console"], "level": "INFO"}
    # Django's own logger writes once, through the same handler.
    assert logging["loggers"]["django"] == {
        "handlers": ["console"],
        "level": "INFO",
        "propagate": False,
    }
    logging = load_settings(**PRODUCTION_ENV, LOG_LEVEL="warning")["LOGGING"]
    assert (
        logging["root"]["level"] == logging["loggers"]["django"]["level"] == "WARNING"
    )


def test_development_mail_goes_to_the_console(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    }
    assert loaded["DEFAULT_FROM_EMAIL"] == "noreply@erplora.com"
    # Even with the SES region of production in the environment, DEBUG never sends real mail.
    loaded = load_settings(**DEVELOPMENT_ENV, SES_REGION="eu-west-1")
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    }


def test_production_mail_goes_through_the_ses_api_with_the_task_role(load_settings):
    # ECS passes SES_REGION and its task role may ses:SendRawEmail: no SMTP credentials, no static keys.
    loaded = load_settings(
        **PRODUCTION_ENV, SES_REGION="eu-west-1", EMAIL_HOST="smtp.example.com"
    )
    assert loaded["MAILERS"] == {"default": {"BACKEND": "django_ses.SESBackend"}}
    assert loaded["AWS_SES_REGION_NAME"] == "eu-west-1"
    assert loaded["AWS_SES_REGION_ENDPOINT"] == "email.eu-west-1.amazonaws.com"
    # The throttle would first call ses:GetSendQuota, which the task role may not.
    assert loaded["AWS_SES_AUTO_THROTTLE"] is None
    assert (
        not {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SES_ACCESS_KEY_ID"}
        & loaded.keys()
    )


def test_the_ses_backend_builds_from_the_settings_so_its_library_is_installed(
    load_settings,
):
    # Built the way Django 6.1 builds a mailer (alias + OPTIONS); building neither connects nor signs.
    loaded = load_settings(**PRODUCTION_ENV, SES_REGION="eu-west-1")
    ses_settings = {
        key: value for key, value in loaded.items() if key.startswith("AWS_SES_")
    }
    with override_settings(MAILERS=loaded["MAILERS"], **ses_settings):
        backend = mailers.default
    assert (
        f"{type(backend).__module__}.{type(backend).__name__}"
        == "django_ses.SESBackend"
    )
    assert (backend._region_name, backend._endpoint_url) == (
        "eu-west-1",
        "https://email.eu-west-1.amazonaws.com",
    )
    assert backend._throttle is None
    # No keys of its own: boto3 signs with the task role.
    assert (backend._access_key_id, backend._access_key, backend._session_token) == (
        None,
        None,
        None,
    )


def test_a_ses_backend_named_by_the_environment_needs_its_region(load_settings):
    with pytest.raises(decouple.UndefinedValueError, match="SES_REGION"):
        load_settings(**PRODUCTION_ENV, EMAIL_BACKEND="django_ses.SESBackend")


def test_production_mail_without_ses_is_smtp_from_the_environment(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert loaded["MAILERS"] == {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": "localhost",
                "port": 587,
                "username": "",
                "password": "",
                "use_tls": True,
                "timeout": 10,
            },
        }
    }
    loaded = load_settings(
        **PRODUCTION_ENV,
        EMAIL_HOST="email-smtp.eu-west-1.amazonaws.com",
        EMAIL_PORT="2587",
        EMAIL_HOST_USER="smtp-user",
        EMAIL_HOST_PASSWORD="smtp-password",
        EMAIL_USE_TLS="False",
        DEFAULT_FROM_EMAIL="hub@erplora.com",
    )
    assert loaded["MAILERS"]["default"]["OPTIONS"] == {
        "host": "email-smtp.eu-west-1.amazonaws.com",
        "port": 2587,
        "username": "smtp-user",
        "password": "smtp-password",
        "use_tls": False,
        "timeout": 10,
    }
    assert loaded["DEFAULT_FROM_EMAIL"] == "hub@erplora.com"


def test_any_mail_backend_from_the_environment_takes_no_smtp_options(load_settings):
    loaded = load_settings(
        **PRODUCTION_ENV, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }


def test_only_the_checks_the_platform_answers_elsewhere_are_silenced():
    # W008: the ALB redirects HTTP to HTTPS, and the SaaS calls /internal over plain HTTP on the private
    # name; W005/W021: HSTS for subdomains and the preload list is the apex's decision (erplora.com).
    assert settings.SILENCED_SYSTEM_CHECKS == [
        "security.W005",
        "security.W008",
        "security.W021",
    ]


def test_check_deploy_is_clean_in_production():
    # A fresh process: the settings of this one are the development ones (.env, DEBUG=True).
    env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
    # SES_REGION as ECS sets it: the SES backend must not trip mail.E001 (development-only backend).
    env |= {
        **PRODUCTION_ENV,
        "SECRET_KEY": secrets.token_urlsafe(50),
        "ALLOWED_HOSTS": ".erplora.com",
        "SES_REGION": "eu-west-1",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_one_letter_hubs_only_in_local_development(load_settings):
    # The local demo hubs are a and b; production enforces live.slugs' minimum of 3.
    assert load_settings(**DEVELOPMENT_ENV)["LIVE"]["hub_slug_min_length"] == 1
    assert load_settings(**PRODUCTION_ENV)["LIVE"]["hub_slug_min_length"] == 3


def test_middleware_order():
    middleware = settings.MIDDLEWARE
    assert middleware[0] == "base.health.HealthCheckMiddleware"
    assert middleware[1:3] == [
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
    ]
    assert "django.middleware.csp.ContentSecurityPolicyMiddleware" in middleware
    locale = middleware.index("django.middleware.locale.LocaleMiddleware")
    assert (
        middleware.index("django.contrib.sessions.middleware.SessionMiddleware")
        < locale
    )
    assert locale < middleware.index("django.middleware.common.CommonMiddleware")


def test_saas_login_runs_after_the_user_is_known():
    middleware = settings.MIDDLEWARE
    saas_login = middleware.index("base.middleware.SaasLoginRequiredMiddleware")
    assert (
        middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
        < saas_login
    )


def test_the_platform_host_gate_runs_after_the_user_is_known_and_before_the_saas_login():
    middleware = settings.MIDDLEWARE
    gate = middleware.index("base.middleware.PlatformHostMiddleware")
    assert (
        middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
        < gate
    )
    # Before SaasLoginRequiredMiddleware and the API envelope: neither runs on the platform host.
    assert gate < middleware.index("base.middleware.SaasLoginRequiredMiddleware")
    assert gate < middleware.index("live.api_errors.ApiErrorEnvelopeMiddleware")


def test_a_host_that_is_no_hub_is_rejected_before_the_session_and_the_api_auth():
    middleware = settings.MIDDLEWARE
    hub_host = middleware.index("base.middleware.HubHostRequiredMiddleware")
    # After CommonMiddleware (ALLOWED_HOSTS), before the user is loaded and ninja checks auth.
    assert middleware.index("django.middleware.common.CommonMiddleware") < hub_host
    assert hub_host < middleware.index(
        "django.contrib.auth.middleware.AuthenticationMiddleware"
    )


def test_api_error_envelope_runs_after_csrf_and_auth():
    middleware = settings.MIDDLEWARE
    envelope = middleware.index("live.api_errors.ApiErrorEnvelopeMiddleware")
    assert middleware.index("django.middleware.csrf.CsrfViewMiddleware") < envelope
    assert (
        middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
        < envelope
    )


def test_templates_expose_the_csp_nonce():
    processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
    assert "django.template.context_processors.csp" in processors


def test_whitenoise_storage_without_manifest_because_vite_already_hashes():
    backend = settings.STORAGES["staticfiles"]["BACKEND"]
    assert backend == "whitenoise.storage.CompressedStaticFilesStorage"
    assert "Manifest" not in backend
    assert settings.STATIC_URL == "/static/"
    assert settings.STATIC_ROOT == BASE_DIR / "staticfiles"


def test_the_hub_files_go_to_the_bucket_terraform_names(load_settings):
    # aws/stacks/prod/apps.tf hands the Hub's task AWS_STORAGE_BUCKET_NAME and AWS_REGION (base.storage).
    loaded = load_settings(**PRODUCTION_ENV, AWS_STORAGE_BUCKET_NAME="erplora-prod-hubs", AWS_REGION="eu-west-1")
    hub_files = loaded["STORAGES"]["hub_files"]
    assert hub_files["BACKEND"] == "storages.backends.s3.S3Storage"
    options = hub_files["OPTIONS"]
    assert (options["bucket_name"], options["region_name"]) == ("erplora-prod-hubs", "eu-west-1")
    # The rest of STORAGES is untouched.
    assert loaded["STORAGES"]["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedStaticFilesStorage"


def test_without_a_bucket_the_hub_files_go_under_media_root(load_settings, tmp_path):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["MEDIA_ROOT"] == BASE_DIR / "media"
    assert loaded["STORAGES"]["hub_files"] == {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": BASE_DIR / "media"},
    }
    moved = load_settings(**DEVELOPMENT_ENV, MEDIA_ROOT=str(tmp_path))
    assert moved["STORAGES"]["hub_files"]["OPTIONS"]["location"] == tmp_path


def test_the_media_directory_is_never_committed():
    assert "media/" in (BASE_DIR / ".gitignore").read_text().splitlines()


def test_only_vite_assets_are_immutable():
    immutable = re.compile(settings.WHITENOISE_IMMUTABLE_FILE_TEST)
    assert immutable.search("/static/spa/assets/main-4f2a.js")
    assert not immutable.search("/static/spa/favicon.svg")
    assert not immutable.search("/static/admin/js/core.js")


def test_spa_build_is_a_static_dir_only_once_built(load_settings):
    dist = BASE_DIR / "frontend" / "dist"
    dirs = load_settings(**DEVELOPMENT_ENV)["STATICFILES_DIRS"]
    assert (("spa", dist) in dirs) is dist.is_dir()


def test_languages_and_time():
    assert settings.LANGUAGE_CODE == "en"
    assert [code for code, _ in settings.LANGUAGES] == ["en", "es"]
    assert settings.USE_TZ is True
    assert settings.TIME_ZONE == "Europe/Madrid"


def test_live_settings():
    live = settings.LIVE
    assert live["context_builder"] == "base.operations.HubContextBuilder"
    assert live["control_alias"] == "default"
    spa = live["spa"]
    assert spa["entry"] == "frontend/main.ts"
    assert spa["manifest"] == BASE_DIR / "frontend" / "dist" / ".vite" / "manifest.json"
    # THEME_PALETTES of packages/ui/src/shell/theme.ts: any other ep_palette cookie paints the default.
    assert spa["palettes"] == [
        "erplora",
        "terracotta",
        "corporate",
        "minimal",
        "forest",
        "ocean",
        "violet",
    ]
    assert spa["palette_default"] == "erplora"
    # Vite runs from the hub's own directory: the repo is its own pnpm workspace (no erplora-next root),
    # on the port this run read (config/settings_pytest.py pins 5173).
    assert live["vite"] == {
        "command": ["env", "VITE_DEV_PORT=5173", "pnpm", "run", "dev"],
        "cwd": str(BASE_DIR),
    }


# ── The `shared` alias: the SaaS's `saas` database, for register_apps only (round 16, PLAN §21) ──


def test_development_always_has_the_shared_alias_on_the_local_saas_database(
    load_settings,
):
    shared = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["shared"]
    assert shared["ENGINE"] == "django.db.backends.postgresql"
    # compose.yaml: one user `hub` for everything, owner of the `saas` database.
    assert (
        shared["NAME"],
        shared["USER"],
        shared["PASSWORD"],
        shared["HOST"],
        shared["PORT"],
    ) == (
        "saas",
        "hub",
        "hub",
        "127.0.0.1",
        5432,
    )
    # Its own test database, where a session fixture creates the schema and the two tables.
    assert shared["TEST"]["NAME"] == "test_hub_next_shared"


def test_the_test_databases_are_named_by_the_environment(load_settings):
    # Two suites at once (two sessions, two checkouts) each pick their own TEST_DB_NAME: with one
    # fixed name the second run finds the database taken and drops or breaks the first's, as
    # saas-next's TEST_DB_NAME.
    databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME="test_hub_sup")[
        "DATABASES"
    ]
    assert databases["default"]["TEST"]["NAME"] == "test_hub_sup"
    assert databases["shared"]["TEST"]["NAME"] == "test_hub_sup_shared"


#: The fleet's recipe: ``test_hub_next_`` and up to 35 characters of its task's key, 49 in all.
LONG_TEST_DB_NAME = "test_hub_next_fix_hub_test_migrator_long_test_db_"
#: The same but for its last character: another session at the same time.
OTHER_LONG_TEST_DB_NAME = "test_hub_next_fix_hub_test_migrator_long_test_db2"
#: What pytest-django appends to every test database under pytest-xdist (``-n``): ``_gw<worker>``.
XDIST_SUFFIXES = ("", "_gw0", "_gw9", "_gw10", "_gw999")


def names_the_suite_derives(databases: dict) -> list[str]:
    """Every database the suite may create from these settings, with and without xdist's suffix: the test databases
    and, from control's, both test hubs' and every template's (``base.tenancy.names``, which refuses a name past
    PostgreSQL's 63 characters instead of truncating it)."""
    from base import catalog
    from base.tenancy import names
    from base.tenancy.tests import hubs

    verticals = (None, hubs.TEMPLATE_VERTICAL, *catalog.known_verticals())
    derived = []
    for suffix in XDIST_SUFFIXES:
        control = databases["default"]["TEST"]["NAME"] + suffix
        derived += [control, *(databases[alias]["TEST"]["NAME"] + suffix for alias in ("shared", "hub_template"))]
        derived += [names.hub_db_name(control, hub_id) for hub_id in (hubs.HUB_A_ID, hubs.HUB_B_ID)]
        derived += [names.template_db_name(control, vertical) for vertical in verticals]
    return derived


@pytest.mark.parametrize(
    "requested",
    # "ñ" * 13: 13 characters but 26 bytes, past the 24 that fit (PostgreSQL's limit counts bytes).
    ["test_hub_next", "test_hub_sup", "t" * 24, "t" * 25, LONG_TEST_DB_NAME, "t" * 63, "ñ" * 13, "ñ" * 40, "t" * 100],
)
def test_every_database_the_suite_derives_from_any_test_db_name_fits_in_postgres(load_settings, requested):
    """A worker never counts characters: whatever TEST_DB_NAME it sets, every name fits (TODO.md, hub#188, hub#204)."""
    from base.tenancy import names

    databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME=requested)["DATABASES"]

    too_long = [name for name in names_the_suite_derives(databases) if len(name.encode()) > names.MAX_IDENTIFIER]
    assert too_long == []


def test_a_test_db_name_that_fits_is_kept_as_it_is(load_settings):
    # --reuse-db and the fleet's sweep.sh find a short name's databases by that name.
    for requested in ("test_hub_next", "t" * 24):
        databases = load_settings(**DEVELOPMENT_ENV, TEST_DB_NAME=requested)["DATABASES"]
        assert databases["default"]["TEST"]["NAME"] == requested


def test_a_long_test_db_name_is_shortened_the_same_every_run_and_apart_from_another(load_settings):
    """Its first characters and the first 8 of its SHA-256 (the sweep recomputes it the same way in a shell): the same
    database every run (--reuse-db, the sweep) and another one for another name (two sessions at once)."""

    def test_names(requested: str) -> dict:
        databases = load_settings(**DEVELOPMENT_ENV, DB_NAME="pre_hub", TEST_DB_NAME=requested)["DATABASES"]
        assert (databases["default"]["NAME"], databases["hub_template"]["NAME"]) == ("pre_hub", "pre_hub_template")
        return {alias: databases[alias]["TEST"]["NAME"] for alias in ("default", "shared", "hub_template")}

    shortened = f"test_hub_next_f_{hashlib.sha256(LONG_TEST_DB_NAME.encode()).hexdigest()[:8]}"
    assert test_names(LONG_TEST_DB_NAME) == {
        "default": shortened,
        "shared": f"{shortened}_shared",
        "hub_template": f"{shortened}_template",
    }
    assert test_names(OTHER_LONG_TEST_DB_NAME)["default"] not in (shortened, OTHER_LONG_TEST_DB_NAME)


def test_the_hubs_template_alias_is_named_after_control_and_reaches_it_directly_in_development(load_settings):
    """Phase 2, S1: every hub's alias copies hub_template (base.tenancy.connections); locally, the compose Postgres."""
    databases = load_settings(**DEVELOPMENT_ENV, DB_NAME="pre_hub", TEST_DB_NAME="test_hub_sup")["DATABASES"]
    template = databases["hub_template"]

    assert template["NAME"] == "pre_hub_template"
    assert (template["HOST"], template["PORT"]) == (databases["default"]["HOST"], databases["default"]["PORT"])
    assert (template["CONN_MAX_AGE"], template["DISABLE_SERVER_SIDE_CURSORS"]) == (0, True)
    assert template["OPTIONS"] == {"connect_timeout": 5, "prepare_threshold": None}
    assert template["TEST"]["NAME"] == "test_hub_sup_template"


def test_in_aws_the_hubs_go_through_the_pgbouncer_sidecar_without_tls_to_it(load_settings):
    """The sidecar listens on the task's loopback; TLS goes from it to Aurora (PLAN-DB §5), so the alias drops the
    writer's sslmode and certificate and keeps the rest."""
    loaded = load_settings(
        **PRODUCTION_ENV,
        DB_HOST="writer.cluster.eu-west-1.rds.amazonaws.com",
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
        DB_APPLICATION_NAME="hub",
        PGBOUNCER_HOST="127.0.0.1",
        PGBOUNCER_PORT="6432",
    )
    template = loaded["DATABASES"]["hub_template"]

    assert (template["HOST"], template["PORT"]) == ("127.0.0.1", 6432)
    assert template["OPTIONS"] == {"connect_timeout": 5, "application_name": "hub", "prepare_threshold": None}
    assert loaded["DATABASE_ROUTERS"] == ["base.routers.SharedRouter", "base.tenancy.router.TenantRouter"]


def test_the_shared_alias_opens_one_short_connection_without_a_pool(load_settings):
    shared = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["shared"]
    assert shared["CONN_MAX_AGE"] == 0
    assert "pool" not in shared["OPTIONS"]
    assert shared["OPTIONS"] == {"connect_timeout": 5}


def test_production_without_shared_credentials_has_no_shared_alias(load_settings):
    # The web service never writes in `shared`: only the worker task receives SHARED_DB_USER.
    assert "shared" not in load_settings(**PRODUCTION_ENV)["DATABASES"]


def test_production_shared_alias_comes_from_its_secret_with_the_tls_of_every_direct_connection(
    load_settings,
):
    loaded = load_settings(
        **PRODUCTION_ENV,
        SHARED_DB_USER="hub_shared",
        SHARED_DB_PASSWORD="from-secrets-manager",
        DB_HOST="aurora.writer",
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
    )
    shared = loaded["DATABASES"]["shared"]
    assert (shared["NAME"], shared["USER"], shared["PASSWORD"], shared["HOST"]) == (
        "saas",
        "hub_shared",
        "from-secrets-manager",
        "aurora.writer",
    )
    assert shared["OPTIONS"] == {
        "connect_timeout": 5,
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ssl/certs/rds-global-bundle.pem",
    }
    assert shared["CONN_MAX_AGE"] == 0


def test_production_shared_alias_without_its_password_refuses_to_start(load_settings):
    with pytest.raises(decouple.UndefinedValueError, match="SHARED_DB_PASSWORD"):
        load_settings(**PRODUCTION_ENV, SHARED_DB_USER="hub_shared")


def test_the_shared_router_goes_first(load_settings):
    # Phase 2's TenantRouter goes after it and never touches `shared`.
    assert settings.DATABASE_ROUTERS[0] == "base.routers.SharedRouter"
    assert (
        load_settings(**PRODUCTION_ENV)["DATABASE_ROUTERS"][0]
        == "base.routers.SharedRouter"
    )


def test_the_static_files_finders_add_the_documentation_images_of_the_modules():
    # base.catalog.AppImagesFinder publishes apps/<id>/docs/img/ as /static/catalog/<id>/img/ (spec §4.4).
    assert settings.STATICFILES_FINDERS == [
        "django.contrib.staticfiles.finders.FileSystemFinder",
        "django.contrib.staticfiles.finders.AppDirectoriesFinder",
        "base.catalog.AppImagesFinder",
    ]


def test_the_release_comes_from_the_image(load_settings):
    # The build fixes APP_VERSION (the commit's sha) and APP_RELEASED_AT (its time) in the image (spec §4.3).
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert (loaded["APP_VERSION"], loaded["APP_RELEASED_AT"]) == ("", "")
    loaded = load_settings(
        **PRODUCTION_ENV,
        APP_VERSION="4da2a10",
        APP_RELEASED_AT="2026-10-13T20:50:00+02:00",
    )
    assert (loaded["APP_VERSION"], loaded["APP_RELEASED_AT"]) == (
        "4da2a10",
        "2026-10-13T20:50:00+02:00",
    )


def test_the_workbook_translation_model_has_a_default_and_comes_from_the_environment(
    load_settings,
):
    assert (
        load_settings(**DEVELOPMENT_ENV)["WORKBOOK_TRANSLATION_MODEL"]
        == "claude-haiku-5-5"
    )
    loaded = load_settings(
        **DEVELOPMENT_ENV, WORKBOOK_TRANSLATION_MODEL="claude-opus-5-5"
    )
    assert loaded["WORKBOOK_TRANSLATION_MODEL"] == "claude-opus-5-5"


def test_the_test_run_keeps_its_cache_in_memory_even_with_a_valkey_in_the_environment():
    # conftest.py empties the cache around every test (base.throttle's attempt counts): pointed at a real Valkey, that
    # would wipe whatever it holds. The test settings keep the process's memory whatever VALKEY_URL says.
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
    assert result.stdout.strip() == "django.core.cache.backends.locmem.LocMemCache"
    assert settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
