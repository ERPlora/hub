"""The tips app declares its module metadata, its permissions and what each role gets."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, CheckoutStep, LiveAppConfig, module_configs, permissions_for_role
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


def test_it_is_in_the_store_and_in_the_restaurant_and_hair_salon_templates():
    assert str(config().verbose_name) == "Tips"
    assert 0 < len(str(config().summary)) <= 120
    assert str(config().description)
    assert config().listed is True
    assert sorted(config().verticals) == ["hair_salon", "restaurant"]


def test_its_menu_opens_the_tips_and_the_settings_to_whoever_manages_them():
    # Whoever only records tips sees neither: their own tips come with «My tips».
    assert [(nav.id, nav.path, nav.permission) for nav in config().navigation] == [
        ("tips", "/tip/tips", "tip.manage"),
        ("settings", "/tip/settings", "tip.manage"),
    ]
    assert [str(nav.label) for nav in config().navigation] == ["Tips", "Settings"]
    for nav in config().navigation:
        assert f"'{nav.icon.removeprefix('ion:')}'" in shell_icon_registry(), nav.id


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
        "tip.suggestion.get",
        "tip.tip.add",
        "tip.tip.get",
        "tip.tip.list",
        "tip.tip.update",
        "tip.tip.void",
    ]


def test_it_adds_its_step_to_the_charge_for_whoever_records_tips():
    # Sales mounts it between the amount and the tenders without knowing Tips (SALE-F39, TIP-F02).
    assert config().checkout == [CheckoutStep(key="tip", component="TipStep", permission="tip.add_tip")]


def test_every_operation_is_described_for_the_assistant():
    for name, op in registry.items():
        if name.startswith("tip."):
            assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), name
