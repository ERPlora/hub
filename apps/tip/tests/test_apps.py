"""The tips app declares its module metadata, its permissions and what each role gets."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, module_configs, permissions_for_role
from live.operations import registry

from base.tests.shell_icons import shell_icon_registry

PERMISSIONS = ["tip.view_tip", "tip.add_tip", "tip.manage", "tip.manage_settings"]


def config():
    return apps.get_app_config("tip")


def test_it_is_an_installed_live_app():
    assert isinstance(config(), LiveAppConfig)
    assert config().name == "apps.tip"
    assert "apps.tip" in settings.INSTALLED_APPS


def test_it_requires_what_it_reads_and_records_in():
    # A tip goes with its sale and its payment method (Sales), enters the open drawer (Cash register) and belongs to a
    # member of the team (Staff).
    assert config().requires == ["sale", "cash_register", "staff"]


def test_it_is_a_free_module_of_the_people_group_with_a_registered_icon():
    assert config().kind == "app"
    assert config() in module_configs()
    assert config().category is Category.PEOPLE
    assert config().premium is False
    assert f"'{config().icon.removeprefix('ion:')}'" in shell_icon_registry()


def test_it_stays_out_of_the_store_and_of_every_template_until_it_has_its_screens():
    assert str(config().verbose_name) == "Tips"
    assert 0 < len(str(config().summary)) <= 120
    assert str(config().description)
    # A business that turned it on, or a new restaurant or hair salon born with it, would find no screen of it: only
    # the API and the assistant would reach it.
    assert config().listed is False
    assert config().verticals == []


def test_permissions():
    assert list(config().permissions) == PERMISSIONS


def test_what_each_role_may_do():
    for role in ("hub_owner", "hub_admin"):
        assert permissions_for_role([config()], role) == set(PERMISSIONS), role
    assert permissions_for_role([config()], "hub_manager") == {"tip.view_tip", "tip.add_tip", "tip.manage"}
    assert permissions_for_role([config()], "hub_employee") == {"tip.view_tip", "tip.add_tip"}


def test_its_operations_are_the_ones_of_this_layer():
    assert sorted(name for name in registry if name.startswith("tip.")) == [
        "tip.sale.refund",
        "tip.sale.void",
        "tip.settings.get",
        "tip.settings.update",
        "tip.tip.add",
        "tip.tip.get",
        "tip.tip.list",
        "tip.tip.update",
        "tip.tip.void",
    ]


def test_every_operation_is_described_for_the_assistant():
    for name, op in registry.items():
        if name.startswith("tip."):
            assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), name
