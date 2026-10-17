"""The tax app declares its module metadata, its menu entries, its permissions and what each role gets."""

from django.apps import apps
from django.conf import settings
from live.meta import Category, LiveAppConfig, Nav, module_configs, permissions_for_role


def tax():
    return apps.get_app_config("tax")


def test_tax_is_an_installed_live_app():
    config = tax()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.tax"
    assert "apps.tax" in settings.INSTALLED_APPS
    # Taxes depends on no other app: inventory, service, sale and invoice depend on it.
    assert config.requires == []


def test_tax_is_a_free_module_of_the_sales_group():
    config = tax()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    assert config.icon == "ion:calculator-outline"


def test_tax_is_in_the_store_and_in_both_verticals():
    # Every hair salon and every restaurant turns it on at sign-up: no sale is priced without it.
    config = tax()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    # Viewing includes calculating: the old `calculate_tax` went to the very same roles as `view_tax`.
    assert tax().permissions == ["tax.view", "tax.manage"]


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(tax().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_roles():
    config = tax()
    assert permissions_for_role([config], "hub_owner") == {"tax.view", "tax.manage"}
    assert permissions_for_role([config], "hub_admin") == {"tax.view", "tax.manage"}
    assert permissions_for_role([config], "hub_manager") == {"tax.view", "tax.manage"}
    # The old cashier and employee roles only consulted and calculated: both are hub_employee now.
    assert permissions_for_role([config], "hub_employee") == {"tax.view"}


def test_navigation_is_the_four_tabs_with_iconify_icons():
    # The icons are the frontend tabbar's (apps/tax/frontend/tabs.ts) and the old menu's
    # (`pricetags`, `receipt`, `swap-horizontal`), all registered in the shell: an unregistered one
    # paints nothing (and HubIcon throws in development).
    entries = tax().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("categories", "Categories", "/tax/categories", "ion:pricetags-outline"),
        ("rules", "Rules", "/tax/rules", "ion:receipt-outline"),
        ("aliases", "Aliases", "/tax/aliases", "ion:swap-horizontal-outline"),
        # The business's tax region (TAX-F11), as Sales and Inventory keep their own settings.
        ("settings", "Settings", "/tax/settings", "ion:settings-outline"),
    ]


def test_every_operation_is_described_for_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: it sees every
    # operation, and a write says how risky it is (high: fiscal, bulk).
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("tax.")}
    assert len(ops) == 18
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name
