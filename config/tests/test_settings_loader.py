"""A settings test imports config.settings anew; when its patches are undone, the process has its own settings back."""

import sys

import decouple
import pytest

from config.tests import test_settings

load_settings = test_settings.load_settings


def settings_modules() -> dict:
    return {name: module for name, module in sys.modules.items() if name.split(".")[:2] == ["config", "settings"]}


@pytest.fixture
def own_settings_back(monkeypatch):
    """Undoes the test's patches, as its end does, and checks every module of the settings is the one from before."""
    modules, attribute = settings_modules(), sys.modules["config"].settings

    def check():
        monkeypatch.undo()
        now = settings_modules()
        assert now.keys() == modules.keys()
        assert [name for name in modules if now[name] is not modules[name]] == []
        assert sys.modules["config"].settings is attribute

    return check


def test_a_load_replaces_the_settings_only_while_its_test_runs(own_settings_back, load_settings):
    before = sys.modules["config.settings"]

    loaded = load_settings(**test_settings.PRODUCTION_ENV)

    assert loaded["DEBUG"] is False
    assert sys.modules["config.settings"] is not before
    assert sys.modules["config"].settings is sys.modules["config.settings"]
    own_settings_back()


def test_two_loads_in_one_test_leave_nothing_behind(own_settings_back, load_settings):
    load_settings(**test_settings.PRODUCTION_ENV)
    assert load_settings(**test_settings.DEVELOPMENT_ENV)["DEBUG"] is True
    own_settings_back()


def test_a_load_the_settings_refuse_leaves_nothing_behind(own_settings_back, load_settings):
    with pytest.raises(decouple.UndefinedValueError, match="SECRET_KEY"):
        load_settings()
    own_settings_back()
