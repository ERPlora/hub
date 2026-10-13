"""The base app is the platform: a LiveAppConfig of kind "platform", always on and never a module.

Round 15 (PLAN §20) supersedes "base is a plain AppConfig": every app of ours extends LiveAppConfig
so the live checks see it, and ``kind`` tells the platform from the modules a hub turns on and off.
"""

from django.apps import apps
from django.core import checks
from live.meta import LiveAppConfig, all_live_app_configs, module_configs


def base():
    return apps.get_app_config("base")


def test_base_is_the_platform_app():
    config = base()
    assert config.name == "base"
    assert isinstance(config, LiveAppConfig)
    assert type(config).__name__ == "BaseConfig"
    assert config.kind == "platform"


def test_base_is_one_of_ours_but_not_a_module():
    assert base() in all_live_app_configs()
    assert base() not in module_configs()


def test_base_declares_no_module_fields():
    config = base()
    assert (config.requires, config.navigation, config.category, config.premium) == ([], [], None, False)


def test_every_installed_app_passes_the_live_checks():
    """base as a platform app and every module of apps/ with its metadata (live.checks)."""
    assert checks.run_checks(tags=["live"]) == []
