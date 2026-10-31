"""The inventory app declares its module metadata, its menu entry, its permissions, what each role gets and its
hooks of the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    Category,
    LiveAppConfig,
    Nav,
    SetupCheck,
    SetupStep,
    Widget,
    module_configs,
    permissions_for_role,
)
from live.operations import registry

from apps.inventory import events as E
from base import home

PERMISSIONS = [
    "inventory.view_product",
    "inventory.view_category",
    "inventory.view_stock",
    "inventory.add_product",
    "inventory.change_product",
    "inventory.delete_product",
    "inventory.add_category",
    "inventory.change_category",
    "inventory.delete_category",
    "inventory.import_product",
    "inventory.export_product",
    "inventory.adjust_stock",
    "inventory.manage_settings",
]
READ_ONLY = {"inventory.view_product", "inventory.view_category", "inventory.view_stock"}


def inventory():
    return apps.get_app_config("inventory")


def test_inventory_is_a_live_app():
    config = inventory()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.inventory"
    assert config.label == "inventory"


def test_inventory_is_a_free_module_of_the_catalog_group():
    config = inventory()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.CATALOG
    assert config.premium is False
    assert config.icon == "ion:cube-outline"
    assert str(config.verbose_name) == "Inventory"


def test_inventory_requires_tax_for_the_fiscal_category_of_each_product():
    # The old manifest's depends_on: ["taxes"]; a product points at a tax.TaxCategory.
    assert inventory().requires == ["tax"]


def test_inventory_is_in_the_store_and_in_the_restaurant_template():
    # Round 16 (PLAN §21): the public store's texts. The restaurant's menu is this catalog; the hair
    # salon's template (PLAN-HUB §7, block 4) does not carry it, a salon turns it on by hand.
    config = inventory()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert inventory().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    # The old `cashier` role does not exist: what it had is what the employee has.
    assert set(inventory().role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}


def test_owner_admin_and_manager_may_do_everything_the_employee_only_reads():
    config = inventory()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == READ_ONLY


def test_navigation_opens_the_inventory_with_an_iconify_icon():
    [entry] = inventory().navigation
    assert isinstance(entry, Nav)
    assert (entry.id, str(entry.label), entry.path) == ("inventory", "Inventory", "/inventory")
    assert entry.icon == "ion:cube-outline"


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    operations = [op for name, op in registry.items() if name.startswith("inventory.")]
    # 31 + the product's image (INVENTORY-F30, F31): set_image, upload_image, suggest_image.
    assert len(operations) == 34
    for op in operations:
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


# The Home's hooks (PLAN-HUB round 2026-10-21; FIX-INVENTORY-SETUP-HOOKS): the old module's module.json `setup` and
# `widgets` (it had no `bell`), on the queries the Panel already reads (INVENTORY-F17, INVENTORY-F28).

PRODUCT_EVENTS = [E.PRODUCT_CREATED, E.PRODUCT_UPDATED, E.PRODUCT_DELETED]


def test_the_homes_step_is_your_catalog_done_with_one_active_product():
    """«Your catalog» (INVENTORY-F28): done as soon as the Panel's figures count one active product, physical or a
    service; whoever may add products sets it up in Inventory → Products."""
    (step,) = inventory().setup
    assert isinstance(step, SetupStep)
    assert (
        step.key,
        step.operation,
        list(step.configured_when),
        dict(step.params),
        step.route,
        step.permission,
        step.icon,
        list(step.countries),
        step.order,
        step.required,
    ) == (
        "catalog",
        "inventory.stock.get_summary",
        [SetupCheck(field="active_products", truthy=True)],
        {},
        "/inventory/products",
        "inventory.add_product",
        "ion:cube-outline",
        [],
        30,
        True,
    )
    assert "active_products" in registry[step.operation].output.model_fields
    # Required, so «Important»; base alone gives the legal level, and an empty catalog stops no invoice.
    assert home.level_of(f"inventory.{step.key}", step.required) == home.LEVEL_FUNCTIONAL


def test_the_step_speaks_the_language_of_whoever_reads_it():
    """gh:hub#868: the old checklist said «Your catalog» in English to a Spanish reader."""
    (step,) = inventory().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == ("Your catalog", "Add at least one product so there is something to sell.")
    assert spanish == ("Tu catálogo", "Añade al menos un producto para que haya algo que vender.")


def test_the_step_is_refreshed_when_a_product_is_added_changed_or_deleted():
    # Turning a product off or deleting the last one sends the step back to pending (INVENTORY-F28, «Si falla»).
    (step,) = inventory().setup
    assert list(step.refresh_on) == PRODUCT_EVENTS
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


PANELS = ["low_stock_count", "value", "in_stock", "low_stock_products"]


def test_the_homes_panels_are_the_old_modules_four():
    """Low-stock count, stock value and the lowest-stock products on by default, products in stock to turn on, each on
    the Panel's own queries (gh:hub#1100: what the old module marked off stays off)."""
    panels = inventory().widgets
    assert all(isinstance(panel, Widget) for panel in panels)
    assert [
        (
            panel.key,
            panel.kind,
            panel.component,
            panel.operation,
            panel.size,
            panel.default,
            panel.permission,
            dict(panel.params),
            dict(panel.map),
            dict(panel.options),
        )
        for panel in panels
    ] == [
        (
            "low_stock_count",
            "kpi",
            None,
            "inventory.stock.get_summary",
            "sm",
            True,
            "inventory.view_product",
            {},
            {"value": "products_low_stock"},
            {"format": "number"},
        ),
        (
            "value",
            "kpi",
            None,
            "inventory.stock.get_summary",
            "sm",
            True,
            "inventory.view_product",
            {},
            {"value": "stock_value"},
            {"format": "currency"},
        ),
        (
            "in_stock",
            "stat",
            None,
            "inventory.stock.get_summary",
            "sm",
            False,
            "inventory.view_product",
            {},
            {"value": "products_in_stock"},
            {"format": "number"},
        ),
        (
            "low_stock_products",
            "bar-list",
            None,
            "inventory.product.list_low_stock",
            "md",
            True,
            "inventory.view_product",
            {"limit": 5},
            {"label": "name", "value": "stock"},
            {"valueFormat": "number"},
        ),
    ]
    # Every business with Inventory on (the old panels named every sector that sells stock), grouped under the app's
    # own name in «Customize panel» (gh:inventory#126: never a literal category).
    assert all(not panel.verticals and not panel.category for panel in panels)
    for panel in panels:
        fields = registry[panel.operation].output.model_fields
        if panel.kind == "bar-list":
            fields = registry[panel.operation].output.model_fields["rows"].annotation.__args__[0].model_fields
        assert set(panel.map.values()) <= set(fields), panel.key


def test_a_kpi_says_its_name_once():
    # gh:hub#1105: the old KPIs painted their header twice (the title and options.label with its icon).
    for panel in inventory().widgets:
        if panel.kind == "kpi":
            assert not {"label", "icon"} & set(panel.options), panel.key


def test_a_money_panel_pins_no_currency_nor_locale():
    """gh:inventory#123 / gh:hub#2391: the stock value is in the hub's currency and the reader's language; a panel
    that fixed EUR and es-ES painted every business in euros, Spanish style."""
    money = [
        panel
        for panel in inventory().widgets
        if "currency" in (panel.options.get("format"), panel.options.get("valueFormat"))
    ]
    assert [panel.key for panel in money] == ["value"]  # a guard that compared nothing would pass for the wrong reason
    for panel in money:
        assert not {"currency", "locale"} & set(panel.options), panel.key


def test_the_panels_are_titled_in_english_and_in_spanish():
    with translation.override("en"):
        english = [str(panel.title) for panel in inventory().widgets]
    with translation.override("es"):
        spanish = [str(panel.title) for panel in inventory().widgets]
    assert english == ["Low-stock products", "Stock value (at cost)", "Products in stock", "Lowest-stock products"]
    assert spanish == [
        "Productos con stock bajo",
        "Valor de existencias (a coste)",
        "Productos en stock",
        "Productos con menos stock",
    ]


def test_each_panel_is_refreshed_by_the_events_that_re_run_its_query():
    """Any stock movement and any product added, changed or deleted, and the settings (which decide what tracks
    stock): the same events that re-run the Panel."""
    panels = {panel.key: panel for panel in inventory().widgets}
    assert list(panels) == PANELS
    for key, panel in panels.items():
        assert list(panel.refresh_on) == [*PRODUCT_EVENTS, E.STOCK_CHANGED, E.CONFIG_UPDATED], key
        assert live_registry.is_subscribable(panel.operation), key
        assert set(panel.refresh_on) == set(live_registry.subscribable[panel.operation]), key


def test_the_hooks_icons_are_registered_in_the_shell():
    # Registered icons only (an unregistered one paints nothing): the old `trending-down-outline` waits in
    # UI-REQUESTS.md.
    (step,) = inventory().setup
    icons = [step.icon, *(panel.icon for panel in inventory().widgets)]
    assert icons == [
        "ion:cube-outline",
        "ion:alert-circle-outline",
        "ion:cash-outline",
        "ion:cube-outline",
        "ion:arrow-down-outline",
    ]
    shell = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for icon in icons:
        assert f"'{icon.removeprefix('ion:')}':" in shell, icon


def test_inventory_has_no_bell_counters():
    # The old module declared none (its module.json has no `bell`).
    assert inventory().bell == []
