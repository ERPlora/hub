"""DEBUG decides development or production: the page's CSP and Vite, what production refuses to start without,
and the security of each request."""

import decouple
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory
from live.csp import YOUTUBE_NOCOOKIE, base_policy, debug_policy, with_frames

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


def with_saas_origin(policy: dict, saas_origin: str) -> dict:
    """``policy`` with its frames (test_settings_frames.py) and the SaaS's origin where the Hub's page reaches it:
    ``form-action`` (the logout's redirect leaves for it), ``img-src`` and ``media-src`` (the WhatsApp attachments it
    serves); ``media-src`` also plays the assistant's answers read aloud in the server's voice, a ``blob:`` of the page."""
    return {
        **with_frames(policy, YOUTUBE_NOCOOKIE),
        "form-action": [*policy["form-action"], saas_origin],
        "img-src": [*policy["img-src"], saas_origin],
        "media-src": ["'self'", "blob:", saas_origin],
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
    # Besides, the page plays its own blob: (the assistant's answer read aloud in the server's voice).
    # Nothing else widens: connect-src keeps the Tauri bridge (ipc:) as live.csp gives it.
    csp = load_settings(**env)["SECURE_CSP"]
    assert csp["img-src"] == [*policy["img-src"], saas_origin]
    assert csp["media-src"] == ["'self'", "blob:", saas_origin]
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
