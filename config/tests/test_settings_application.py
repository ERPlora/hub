"""The apps, the middleware and the templates Django runs, in the order that makes them work."""

from django.conf import settings


def test_live_precedes_daphne_so_its_runserver_wins():
    installed = settings.INSTALLED_APPS
    assert installed.index("live") < installed.index("daphne")
    assert {"ninja", "base", "apps.demo"} <= set(installed)


def test_base_precedes_the_admin_so_its_admin_templates_win():
    # base/templates/admin/base_site.html adds the chosen hub's banner. Django's admin is
    # installed through its config with the Hub's own site (base/admin_site.py: a hub's model only with a business).
    installed = settings.INSTALLED_APPS
    assert "django.contrib.admin" not in installed
    assert installed.index("base") < installed.index("base.admin_site.AdminConfig")


def test_middleware_order():
    middleware = settings.MIDDLEWARE
    assert middleware[0] == "base.health.HealthCheckMiddleware"
    # A cut of the database is waited for outside every other layer (BASE-F111): Django turns an exception into a
    # response at each one, so only the outermost sees the whole request. /healthz reads no database.
    assert middleware[1] == "live.database_cut.DatabaseCutMiddleware"
    assert middleware[2:4] == [
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
