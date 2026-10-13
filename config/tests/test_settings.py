"""hub-next settings: env through decouple, Postgres with a pool, CSP per DEBUG, WhiteNoise, LIVE."""

import re
import runpy
from pathlib import Path

import decouple
import pytest
from django.conf import settings
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
    "INTERNAL_SHARED_SECRET",
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
        monkeypatch.setattr(decouple, "config", decouple.AutoConfig(search_path=str(tmp_path)))
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
    assert (db["NAME"], db["USER"], db["PASSWORD"], db["HOST"], db["PORT"]) == ("hub", "hub", "hub", "127.0.0.1", 5432)
    assert db["OPTIONS"]["pool"] == {"min_size": 1, "max_size": 8}
    # Its own test database, so it never drops the one the packages/live suite is using.
    assert db["TEST"]["NAME"] == "test_hub_next"


def test_database_comes_from_the_environment(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV, DB_NAME="other", DB_HOST="db.internal", DB_PORT="6543")
    db = loaded["DATABASES"]["default"]
    assert (db["NAME"], db["HOST"], db["PORT"]) == ("other", "db.internal", 6543)


def test_debug_defaults_to_false_so_a_missing_variable_never_turns_it_on(load_settings):
    env = {key: value for key, value in PRODUCTION_ENV.items() if key != "DEBUG"}
    loaded = load_settings(**env)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == base_policy()
    assert loaded["LIVE"]["spa"]["dev_server"] is None


def test_without_debug_nor_a_secret_key_the_settings_refuse_to_start(load_settings):
    # No DEBUG means production: the known local key is never a fallback.
    with pytest.raises(decouple.UndefinedValueError, match="SECRET_KEY"):
        load_settings()


def test_development_uses_the_debug_csp_and_vite(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["DEBUG"] is True
    assert loaded["SECURE_CSP"] == debug_policy()
    assert loaded["LIVE"]["spa"]["dev_server"] == "http://localhost:5173"
    assert loaded["ALLOWED_HOSTS"] == [".localhost", "127.0.0.1", "localhost"]


def test_production_uses_the_base_csp_and_no_dev_server(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert loaded["DEBUG"] is False
    assert loaded["SECURE_CSP"] == base_policy()
    assert loaded["LIVE"]["spa"]["dev_server"] is None
    assert loaded["SECRET_KEY"] == "from-the-environment"


@pytest.mark.parametrize("missing", ["SECRET_KEY", "SAAS_URL", "INTERNAL_SHARED_SECRET"])
def test_production_without_a_secret_or_the_saas_refuses_to_start(load_settings, missing):
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
    assert (loaded["SAAS_URL"], loaded["INTERNAL_SHARED_SECRET"]) == ("https://erplora.com", "shared-with-the-saas")


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
    assert middleware.index("django.contrib.sessions.middleware.SessionMiddleware") < locale
    assert locale < middleware.index("django.middleware.common.CommonMiddleware")


def test_saas_login_runs_after_the_user_is_known():
    middleware = settings.MIDDLEWARE
    saas_login = middleware.index("base.middleware.SaasLoginRequiredMiddleware")
    assert middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") < saas_login


def test_the_platform_host_gate_runs_after_the_user_is_known_and_before_the_saas_login():
    middleware = settings.MIDDLEWARE
    gate = middleware.index("base.middleware.PlatformHostMiddleware")
    assert middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") < gate
    # Before SaasLoginRequiredMiddleware and the API envelope: neither runs on the platform host.
    assert gate < middleware.index("base.middleware.SaasLoginRequiredMiddleware")
    assert gate < middleware.index("live.api_errors.ApiErrorEnvelopeMiddleware")


def test_a_host_that_is_no_hub_is_rejected_before_the_session_and_the_api_auth():
    middleware = settings.MIDDLEWARE
    hub_host = middleware.index("base.middleware.HubHostRequiredMiddleware")
    # After CommonMiddleware (ALLOWED_HOSTS), before the user is loaded and ninja checks auth.
    assert middleware.index("django.middleware.common.CommonMiddleware") < hub_host
    assert hub_host < middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")


def test_api_error_envelope_runs_after_csrf_and_auth():
    middleware = settings.MIDDLEWARE
    envelope = middleware.index("live.api_errors.ApiErrorEnvelopeMiddleware")
    assert middleware.index("django.middleware.csrf.CsrfViewMiddleware") < envelope
    assert middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware") < envelope


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
    assert live["apps_dirs"] == [BASE_DIR / "apps"]
    spa = live["spa"]
    assert spa["entry"] == "frontend/main.ts"
    assert spa["manifest"] == BASE_DIR / "frontend" / "dist" / ".vite" / "manifest.json"
    assert spa["palettes"] == ["erplora"]
    assert spa["palette_default"] == "erplora"
    # Vite runs from the hub's own directory: the repo is its own pnpm workspace (no erplora-next root).
    assert live["vite"] == {"command": ["pnpm", "run", "dev"], "cwd": str(BASE_DIR)}
