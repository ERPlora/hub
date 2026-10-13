"""hub-next settings: env through decouple, Postgres with a pool, CSP per DEBUG, WhiteNoise, LIVE."""

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
    assert db["OPTIONS"]["pool"] == {"min_size": 1, "max_size": 8, "timeout": 5}
    # Its own test database, so it never drops the one the packages/live suite is using.
    assert db["TEST"]["NAME"] == "test_hub_next"


def test_database_comes_from_the_environment(load_settings):
    loaded = load_settings(
        **DEVELOPMENT_ENV, DB_NAME="other", DB_HOST="db.internal", DB_PORT="6543"
    )
    db = loaded["DATABASES"]["default"]
    assert (db["NAME"], db["HOST"], db["PORT"]) == ("other", "db.internal", 6543)


def with_saas_form_action(policy: dict, saas_origin: str) -> dict:
    """``policy`` with the SaaS's origin in ``form-action``: the logout's redirect leaves for it."""
    return {**policy, "form-action": [*policy["form-action"], saas_origin]}


def test_debug_defaults_to_false_so_a_missing_variable_never_turns_it_on(load_settings):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DEBUG"}
    loaded = load_settings(**env)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == with_saas_form_action(
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
    assert loaded["SECURE_CSP"] == with_saas_form_action(
        debug_policy(), "http://localhost:8001"
    )
    assert loaded["LIVE"]["spa"]["dev_server"] == "http://localhost:5173"
    assert loaded["ALLOWED_HOSTS"] == [".localhost", "127.0.0.1", "localhost"]


def test_production_uses_the_base_csp_and_no_dev_server(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == with_saas_form_action(
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


def test_database_tls_and_application_name_only_when_set(load_settings):
    options = load_settings(**DEVELOPMENT_ENV)["DATABASES"]["default"]["OPTIONS"]
    assert options == {
        "pool": {"min_size": 1, "max_size": 8, "timeout": 5},
        "connect_timeout": 5,
    }
    loaded = load_settings(
        **PRODUCTION_ENV,
        DB_SSLMODE="verify-full",
        DB_SSLROOTCERT="/etc/ssl/certs/rds-global-bundle.pem",
        DB_APPLICATION_NAME="worker",
    )
    assert loaded["DATABASES"]["default"]["OPTIONS"] == {
        "pool": {"min_size": 1, "max_size": 8, "timeout": 5},
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
    # Vite runs from the hub's own directory: the repo is its own pnpm workspace (no erplora-next root).
    assert live["vite"] == {"command": ["pnpm", "run", "dev"], "cwd": str(BASE_DIR)}


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
