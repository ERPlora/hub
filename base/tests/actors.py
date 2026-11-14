"""Who can do something in a hub, as an operation's context names them (``base.relay.by_platform``)."""

import pytest

from base import recovery
from base.api_keys import KeyCaller

RUN = "0199e7a0-0000-7000-8000-000000000001"


def who_did_it(person, name: str) -> list:
    """``(caller, who, by_platform)`` cases: ``person`` (read as ``name``) and an API key are named; the system, an
    automation's step, a recovery from a copy and no one are the platform, their mark kept as the app saved it."""
    return [
        pytest.param(person, name, False, id="a person"),
        pytest.param(KeyCaller(key_id="k1", name="Zapier", prefix="erpk_live_ab"), "API · Zapier", False, id="an API key"),
        pytest.param("system", "system", True, id="the system"),
        pytest.param(f"flow_run:{RUN}", f"flow_run:{RUN}", True, id="an automation's step"),
        pytest.param(recovery.actor_of(RUN), recovery.actor_of(RUN), True, id="a recovery from a copy"),
        pytest.param(None, "", True, id="no one"),
    ]
