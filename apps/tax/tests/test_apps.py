"""The tax app declares its module metadata, its menu entries, its permissions, what each role gets and its hook of
the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, module_configs, permissions_for_role
from live.operations import registry

from apps.tax import events as E
from base import home


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


# The Home's hook (PLAN-HUB round 2026-10-21; FIX-TAX-SETUP-HOOKS): the old module's own item «Your taxes»
# (module.json `setup`, taxes#19), which reads the same query as the notice of the tax screens (TAX-F17). The old
# module declared no panel and no bell row.


def test_the_homes_step_is_your_taxes_done_once_one_root_rule_applies_today():
    """The old module's item, same order: functional, as it declared it (`required: true`), done once one active root
    rule of any country applies today (the query the notice reads, without a country), for whoever manages taxes,
    leading to the rules (the old `/m/taxes/rules`)."""
    (step,) = tax().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        dict(step.params),
        list(step.configured_when),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "rules",
        "tax.rule.status",
        {},
        [SetupCheck(field="configured", truthy=True)],
        "/tax/rules",
        "tax.manage",
        "ion:receipt-outline",
        [],
        20,
        True,
    )
    assert "configured" in registry[step.operation].output.model_fields
    assert home.level_of(f"tax.{step.key}", step.required) == home.LEVEL_FUNCTIONAL


def test_the_step_says_the_words_of_the_notice_in_the_language_of_whoever_reads_it():
    # gh:hub#2356: the old checklist said a module's step in English to a Spanish reader.
    (step,) = tax().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == ("Your taxes", "Set up the VAT rates of the country you sell in so the till can price a sale.")
    assert spanish == (
        "Tus impuestos",
        "Configura los tipos de IVA del país en el que vendes para que el TPV pueda calcular el precio de una venta.",
    )


def test_the_step_is_refreshed_on_what_changes_the_rules_in_force_today():
    # A rule created (one or many), ended, deactivated or activated. Never the business's region: the step counts the
    # rules of any country and any region, so the region changes nothing.
    (step,) = tax().setup
    assert list(step.refresh_on) == E.RULE_IN_FORCE_EVENTS
    assert set(E.RULE_IN_FORCE_EVENTS) == {
        "tax.rule.created",
        "tax.rule.ended",
        "tax.rule.deactivated",
        "tax.rule.activated",
    }
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


def test_the_steps_icon_is_registered():
    # The old module's `receipt`, the icon of the Rules tab.
    (step,) = tax().setup
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    assert f"'{step.icon.removeprefix('ion:')}'" in icons


def test_taxes_brings_no_panels_and_no_bell_rows_to_the_home():
    # The old module declared neither (its module.json has `widgets` and `bell` null).
    assert (tax().widgets, tax().bell) == ([], [])
