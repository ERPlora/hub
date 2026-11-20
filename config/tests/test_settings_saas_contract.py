"""The SaaS the Hub talks to: its addresses, the secret /internal shares with it and the assistant's voice."""

import pytest

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


@pytest.mark.parametrize(("env", "on"), [({}, False), ({"ASSISTANT_SERVER_VOICE": "True"}, True)])
def test_the_server_voice_of_the_assistant_is_off_unless_the_environment_turns_it_on(load_settings, env, on):
    """No voice provider is configured: the panel reads with the device's voice."""
    assert load_settings(**PRODUCTION_ENV, **env)["ASSISTANT_SERVER_VOICE"] is on


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
