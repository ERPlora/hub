"""VeriFactu's switches of the server, read from the environment."""

import pytest

from config.tests import settings_env

ROUTE = "VERIFACTU_ERPLORA_ROUTE_ENABLED"


@pytest.mark.parametrize("env", [settings_env.PRODUCTION_ENV, settings_env.DEVELOPMENT_ENV])
def test_erploras_route_is_open_unless_the_environment_closes_it(load_settings, monkeypatch, env):
    """Open by default, so a deployment changes nothing until it says otherwise; ``pre`` closes it."""
    monkeypatch.delenv(ROUTE, raising=False)
    assert load_settings(**env)[ROUTE] is True
    assert load_settings(**env, **{ROUTE: "false"})[ROUTE] is False
    assert load_settings(**env, **{ROUTE: "true"})[ROUTE] is True
