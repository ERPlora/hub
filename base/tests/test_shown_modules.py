"""Which modules bring their hooks to the Home of a scope."""

from types import SimpleNamespace

from base import home


def config(label, listed=True):
    return SimpleNamespace(label=label, listed=listed)


def test_only_the_modules_on_in_the_scope_bring_their_hooks(monkeypatch, settings):
    settings.SHOW_UNLISTED_MODULES = True
    monkeypatch.setattr("base.home.shown_modules.module_configs", lambda: [config("sale"), config("stock"), config("demo", False)])

    assert [c.label for c in home.shown_modules.home_modules({"sale", "demo", "base"})] == ["sale", "demo"]


def test_a_module_out_of_the_store_brings_none_unless_the_setting_says_so(monkeypatch, settings):
    """``demo`` (``listed = False``) is the platform's reference, not a customer's app: its example step, panel and
    counter are for the tests and the e2e (``SHOW_UNLISTED_MODULES``, on with ``DEBUG``), never for a customer."""
    monkeypatch.setattr("base.home.shown_modules.module_configs", lambda: [config("sale"), config("demo", False)])

    settings.SHOW_UNLISTED_MODULES = False
    assert [c.label for c in home.shown_modules.home_modules({"sale", "demo"})] == ["sale"]
    settings.SHOW_UNLISTED_MODULES = True
    assert [c.label for c in home.shown_modules.home_modules({"sale", "demo"})] == ["sale", "demo"]


def test_the_setting_is_off_in_production_and_on_with_debug():
    from django.conf import settings

    from config import settings as hub_settings

    assert hub_settings.SHOW_UNLISTED_MODULES == hub_settings.DEBUG
    assert settings.SHOW_UNLISTED_MODULES is True  # the suite runs with the development settings
