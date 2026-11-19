"""The keys that seal what a business keeps: the automations' secrets and its own fiscal certificate."""

from config.tests.settings_env import PRODUCTION_ENV


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
