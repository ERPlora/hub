"""The inventory app declares its module metadata, its menu entries, its permissions, what each role gets, its help
and its hooks of the Home."""

from pathlib import Path

from django.apps import apps
from django.utils import translation
from live.context import OperationContext
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
from live.operations import AI, INTERNAL, get, registry

from apps.inventory import events as E
from base import home
from base.queries import app_help
from base.schemas.app_help import AppHelpIn
from base.tenancy.tests.business import HUB_DB, A
from base.tests.shell_icons import shell_icon_registry

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
    # The app store's texts. The restaurant's menu is this catalog; the hair salon's template does not carry it, a
    # salon turns it on by hand.
    config = inventory()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["restaurant"]
    assert config.listed is True


def test_permissions_are_the_workbook_ones():
    assert list(inventory().permissions) == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    # The old `cashier` role does not exist: what it had is what the employee has.
    assert set(inventory().role_permissions) == {"hub_owner", "hub_admin", "hub_manager", "hub_employee"}


def test_owner_admin_and_manager_may_do_everything_the_employee_only_reads():
    config = inventory()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    assert permissions_for_role([config], "hub_employee") == READ_ONLY


FRONTEND = Path(apps.get_app_config("inventory").path) / "frontend"


def test_the_menu_has_the_tab_bar_s_screens_with_the_launcher_s_icon_first():
    # The tab bar shows the entries the person may open, the help window names the screen in view by them and the
    # assistant links each one, each with the permission that opens it. The first one keeps the cube: it is the icon of
    # the launcher and of «My apps» (base.home.shell_icon).
    entries = inventory().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [(entry.id, str(entry.label), entry.path, entry.icon, entry.permission) for entry in entries] == [
        ("dashboard", "Dashboard", "/inventory/dashboard", "ion:cube-outline", "inventory.view_stock"),
        ("products", "Products", "/inventory/products", "ion:cube-outline", "inventory.view_product"),
        ("movements", "Movements", "/inventory/movements", "ion:swap-vertical-outline", "inventory.view_stock"),
        ("categories", "Categories", "/inventory/categories", "ion:list-outline", "inventory.view_category"),
        ("settings", "Settings", "/inventory/settings", "ion:settings-outline", "inventory.manage_settings"),
    ]
    assert home.shell_icon(inventory()) == "ion:cube-outline"
    shell = shell_icon_registry()
    for entry in entries:
        assert f"'{entry.icon.removeprefix('ion:')}':" in shell, entry.icon


def test_the_launcher_opens_where_the_inventory_s_root_lands():
    # The launcher and «My apps» open the first entry; `/inventory` hands over to that same screen.
    routes = (FRONTEND / "routes.ts").read_text(encoding="utf-8")
    assert f"{{ path: '/inventory', redirect: '{inventory().navigation[0].path}'" in routes


def test_the_help_window_s_tabs_are_the_menu_s_entries():
    assert [(tab.id, tab.path) for tab in app_help.tabs_of(inventory())] == [
        (entry.id, entry.path) for entry in inventory().navigation
    ]


def test_its_help_window_plays_how_inventory_works_in_spanish_and_in_english():
    assert inventory().help.videos == {"es": "dIppfjMEKWo", "en": "Pet7Q2ayo_Y"}


def read_help(language: str):
    ctx = OperationContext(scope=A, actor="ana", permissions=frozenset({"base.view_home"}), language=language)
    return get("base.help.get")(ctx, AppHelpIn(app="inventory"))


@HUB_DB
def test_the_help_window_gets_the_video_in_the_person_s_language():
    videos = [read_help(language).video for language in ("es", "en", "en-gb")]
    assert videos == ["dIppfjMEKWo", "Pet7Q2ayo_Y", "Pet7Q2ayo_Y"]


#: The short video of each task, by the flows it shows: its Spanish and its English one.
TASK_VIDEOS = [
    (("INVENTORY-F01", "INVENTORY-F02", "INVENTORY-F04"), "L4LipaZOq40", "hzMXqJHeFos"),
    (("INVENTORY-F30", "INVENTORY-F31"), "yBhRFR1f_6E", "Z1MtnTUSGPQ"),
    (("INVENTORY-F35",), "DFK01vdQIVE", "FUzkFMxT0ic"),
    (("INVENTORY-F29", "INVENTORY-F03"), "GL4yDJmLYSA", "ekG-0-deeVc"),
    (("INVENTORY-F09",), "VJYcIj1zuDU", "biNLckdpSyg"),
    (("INVENTORY-F11",), "QPklnAbvc58", "RLScnZGT6qU"),
    (("INVENTORY-F13",), "bT10ePok7D0", "-wCJF6Slq2E"),
    (("INVENTORY-F14",), "UhYUS4HjOOU", "WuR4YbL1isc"),
    (("INVENTORY-F15",), "O3U9Jejg13Y", "sARCVGUjtwQ"),
    (("INVENTORY-F26",), "Yek9FtgeJGc", "mh-mnQbzXEc"),
    (("INVENTORY-F20",), "Vwb3kAQ9O4U", "ZGFEjiIzjuo"),
    (("INVENTORY-F06", "INVENTORY-F07"), "T9mYixTpiiU", "uu2RtLPsHkQ"),
    (("INVENTORY-F08",), "A47AOMAoQdo", "ovjk6OQA-78"),
    (("INVENTORY-F16",), "GkYZip01B5s", "96AlQ2-UR-s"),
    (("INVENTORY-F10",), "Zde0OM4WtlM", "MecB51iNSrI"),
]


@HUB_DB
def test_each_task_of_the_help_window_shows_its_short_video_in_the_person_s_language():
    def videos(language: str) -> dict[str, list[str]]:
        return {flow.id: flow.videos for flow in read_help(language).flows if flow.videos}

    assert videos("es") == {flow: [es] for flows, es, _en in TASK_VIDEOS for flow in flows}
    assert videos("en") == {flow: [en] for flows, _es, en in TASK_VIDEOS for flow in flows}


#: The reads that only name a record on the assistant's card: no tool, no route.
CARD_ONLY = {"inventory.category.get"}
#: The writes whose card says their data by a summary of their own: the rows of a file by their names.
CARD_SUMMARY = {"inventory.product.bulk_create", "inventory.category.bulk_create"}


def test_every_operation_is_a_tool_of_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: the operation's
    # permission is its only door. A command says its risk; a read has none.
    operations = [op for name, op in registry.items() if name.startswith("inventory.")]
    # 31 + the product's image (INVENTORY-F30, F31): set_image, upload_image, suggest_image; + the category the
    # assistant's card names; + the restore of a deleted product, the recovery of a deleted category and of a product
    # no longer held, the platform's alone (INVENTORY-F34, INVENTORY-F07, BASE-F114).
    assert len(operations) == 38
    for op in operations:
        if op.name in CARD_ONLY:
            assert op.ai is INTERNAL and op.expose_api is False, op.name
            continue
        assert isinstance(op.ai, dict) and op.ai.get("description"), op.name
        expected = {"description", "risk"} if op.kind == "command" else {"description"}
        if isinstance(op.ai_spec(), AI):  # a tool says what a person types to ask for it (live.E020)
            expected |= {"asks"}
        if op.name in CARD_SUMMARY:
            expected |= {"summary"}
        assert set(op.ai) == expected, op.name
        if op.kind == "command":
            assert op.ai["risk"] in {"normal", "high"}, op.name


# The Home's hooks, on the queries the Panel already reads (INVENTORY-F17, INVENTORY-F28).

PRODUCT_EVENTS = [E.PRODUCT_CREATED, E.PRODUCT_UPDATED, E.PRODUCT_DELETED, E.PRODUCT_RESTORED]


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
    """A Spanish reader never reads «Your catalog» in English."""
    (step,) = inventory().setup
    with translation.override("en"):
        english = (str(step.title), str(step.description))
    with translation.override("es"):
        spanish = (str(step.title), str(step.description))
    assert english == ("Your catalog", "Add at least one product so there is something to sell.")
    assert spanish == ("Tu catálogo", "Añade al menos un producto para que haya algo que vender.")


def test_the_step_is_refreshed_when_a_product_is_added_changed_deleted_or_restored():
    # Turning a product off or deleting the last one sends the step back to pending (INVENTORY-F28, «Si falla»); a
    # deleted one brought back counts again (INVENTORY-F34).
    (step,) = inventory().setup
    assert list(step.refresh_on) == PRODUCT_EVENTS
    assert set(step.refresh_on) <= set(live_registry.subscribable[step.operation])


PANELS = ["low_stock_count", "value", "in_stock", "low_stock_products"]


def test_the_homes_panels_are_the_old_modules_four():
    """Low-stock count, stock value and the lowest-stock products on by default, products in stock to turn on, each on
    the Panel's own queries: what the old module marked off stays off."""
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
            {"format": "number", "tone": 6},
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
            {"format": "currency", "tone": 6},
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
            {"format": "number", "tone": 6},
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
    # own name in «Customize panel», never a literal category.
    assert all(not panel.verticals and not panel.category for panel in panels)
    for panel in panels:
        fields = registry[panel.operation].output.model_fields
        if panel.kind == "bar-list":
            fields = registry[panel.operation].output.model_fields["rows"].annotation.__args__[0].model_fields
        assert set(panel.map.values()) <= set(fields), panel.key


def test_a_kpi_says_its_name_once():
    # Never the header twice (the title and options.label with its icon).
    for panel in inventory().widgets:
        if panel.kind == "kpi":
            assert not {"label", "icon"} & set(panel.options), panel.key


def test_a_money_panel_pins_no_currency_nor_locale():
    """The stock value is in the hub's currency and the reader's language; a panel that fixed EUR and es-ES painted
    every business in euros, Spanish style."""
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
    """Any stock movement and any product added, changed, deleted or restored, and the settings (which decide what tracks
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
    shell = shell_icon_registry()
    for icon in icons:
        assert f"'{icon.removeprefix('ion:')}':" in shell, icon


def test_its_figures_carry_the_colour_of_inventory():
    # The same measure keeps the same colour of data on every screen: inventory is 6. The list of products is no figure.
    panels = {panel.key: panel for panel in inventory().widgets}
    assert {key: panel.options.get("tone") for key, panel in panels.items()} == {
        "low_stock_count": 6,
        "value": 6,
        "in_stock": 6,
        "low_stock_products": None,
    }


def test_inventory_has_no_bell_counters():
    # The old module declared none (its module.json has no `bell`).
    assert inventory().bell == []
