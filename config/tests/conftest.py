import importlib
import sys

import decouple
import pytest

from config.tests.settings_env import ENV_KEYS, SETTINGS_PACKAGE


@pytest.fixture
def load_settings(monkeypatch, tmp_path):
    """Import config.settings anew with only the given environment (no .env file); its old modules return after."""
    def load(**env: str) -> dict:
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(decouple, "config", decouple.AutoConfig(search_path=str(tmp_path)))
        monkeypatch.setattr(sys.modules["config"], "settings", sys.modules["config"].settings)
        for name in [name for name in sys.modules if name.split(".")[:2] == SETTINGS_PACKAGE.split(".")]:
            monkeypatch.delitem(sys.modules, name)
        return vars(importlib.import_module(SETTINGS_PACKAGE))

    return load
