"""The sale app declares its module metadata, its menu entries, its permissions, what each role gets and its panels
of the Home."""

from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.utils import translation
from live.live_registry import live_registry
from live.meta import (
    Category,
    LiveAppConfig,
    Nav,
    Widget,
    module_configs,
    permissions_for_role,
)

PERMISSIONS = [
    "sale.view_sale",
    "sale.add_sale",
    "sale.take_payment",
    "sale.sell_open_price",
    "sale.discount_over_limit",
    "sale.void_sale",
    "sale.refund_sale",
    "sale.view_paymentmethod",
    "sale.add_paymentmethod",
    "sale.view_reports",
    "sale.manage_settings",
]


def sale():
    return apps.get_app_config("sale")


def test_sale_is_an_installed_live_app():
    config = sale()
    assert isinstance(config, LiveAppConfig)
    assert config.name == "apps.sale"
    assert "apps.sale" in settings.INSTALLED_APPS


def test_it_requires_tax_and_customer_but_not_inventory():
    # Every line is priced with tax's rules and a sale keeps its customer's card (a foreign key).
    # Inventory is optional (PLAN §20.5): the till sells services and open prices without it, a
    # line keeps a copy of its product, and inventory moves the stock by reacting to the sale.
    assert sale().requires == ["tax", "customer"]


def test_sale_is_a_free_module_of_the_sales_group():
    config = sale()
    assert config.kind == "app"
    assert config in module_configs()
    assert config.category is Category.SALES
    assert config.premium is False
    assert config.icon == "ion:cart-outline"


def test_sale_is_in_the_store_and_in_both_verticals():
    config = sale()
    assert 0 < len(str(config.summary)) <= 120
    assert str(config.description)
    assert config.verticals == ["hair_salon", "restaurant"]
    assert config.listed is True


def test_permissions():
    # The product's fifteen, but for the four no operation asks for (delete_sale, change_sale,
    # change_paymentmethod, delete_paymentmethod) and with `discount.over_limit` as one action.
    assert sale().permissions == PERMISSIONS


def test_roles_are_the_four_customer_roles_with_the_hub_prefix():
    assert set(sale().role_permissions) == {
        "hub_owner",
        "hub_admin",
        "hub_manager",
        "hub_employee",
    }


def test_roles():
    config = sale()
    for role in ("hub_owner", "hub_admin", "hub_manager"):
        assert permissions_for_role([config], role) == set(PERMISSIONS), role
    # The old cashier (the employee who also charges) is the employee now: it builds the check,
    # charges it and reads the sales; voiding, refunding, figures and settings are the manager's.
    assert permissions_for_role([config], "hub_employee") == {
        "sale.view_sale",
        "sale.add_sale",
        "sale.take_payment",
        "sale.view_paymentmethod",
    }


def test_navigation_is_the_old_four_tabs_and_the_settings():
    # Registered icons only: the old `storefront` (filled) and `chatbubble-ellipses-outline` wait in
    # UI-REQUESTS.md. The settings were a tab the old hub added; here they are the app's own page.
    entries = sale().navigation
    assert all(isinstance(entry, Nav) for entry in entries)
    assert [
        (entry.id, str(entry.label), entry.path, entry.icon) for entry in entries
    ] == [
        ("pos", "Sell", "/sale/pos", "ion:storefront-outline"),
        ("sales", "Sales", "/sale/sales", "ion:cart-outline"),
        ("quick_notes", "Quick notes", "/sale/quick-notes", "ion:chatbubbles-outline"),
        ("departments", "Sections", "/sale/departments", "ion:grid-outline"),
        ("settings", "Settings", "/sale/settings", "ion:settings-outline"),
    ]


def test_every_operation_is_described_for_the_assistant():
    # The assistant uses the app by voice and text with the user's own session: it sees every
    # operation, and a write says how risky it is (high: money moves or a sale is corrected).
    from live.operations import registry

    ops = {name: op for name, op in registry.items() if name.startswith("sale.")}
    assert ops
    for name, op in ops.items():
        assert isinstance(op.ai, dict) and str(op.ai.get("description", "")).strip(), (
            name
        )
        if op.kind == "command":
            assert op.ai.get("risk") in {"normal", "high"}, name
        else:
            assert "risk" not in op.ai, name


def test_the_money_and_fiscal_writes_are_high_risk():
    from live.operations import registry

    high = {
        name
        for name, op in registry.items()
        if name.startswith("sale.") and op.ai.get("risk") == "high"
    }
    assert {
        "sale.sale.complete",
        "sale.sale.complete_over_limit",
        "sale.sale.void",
        "sale.sale.refund",
        "sale.sale.issue_documents",
        "sale.order.void",
        "sale.order.void_line",
        "sale.order.set_discount",
        "sale.order.set_discount_over_limit",
        "sale.order.set_line_discount",
        "sale.order.set_line_discount_over_limit",
    } <= high


# ── The Home's hooks (PLAN-HUB round 2026-10-21) ────────────────────────────────────────────────────

FIGURES = ["sale.sale.completed", "sale.sale.voided", "sale.sale.refunded"]
SALES = [*FIGURES, "sale.sale.reassigned", "sale.sale.invoiced"]


def test_the_homes_panels_are_the_old_sales_dashboards_four():
    """The old module's four panels of the dashboard (its module.json ``widgets``): today's sales and tickets on
    by default, the last seven days and the recent activity to turn on, each on a query of queries.py."""
    panels = sale().widgets
    assert all(isinstance(panel, Widget) for panel in panels)
    assert [
        (
            panel.key,
            panel.kind,
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
            "today",
            "kpi",
            "sale.sale.today",
            "sm",
            True,
            "sale.view_reports",
            {},
            {"value": "total"},
            {"format": "currency"},
        ),
        (
            "tickets_today",
            "kpi",
            "sale.sale.today",
            "sm",
            True,
            "sale.view_reports",
            {},
            {"value": "tickets"},
            {"format": "number"},
        ),
        (
            "last_7_days",
            "chart",
            "sale.sale.last_7_days",
            "lg",
            False,
            "sale.view_reports",
            {},
            {"label": "day", "value": "total"},
            {"format": "currency"},
        ),
        (
            "recent_activity",
            "timeline",
            "sale.sale.list",
            "md",
            False,
            "sale.view_sale",
            {"limit": 8, "sort": "created_at", "dir": "desc"},
            {"title": "number", "description": "customer_name", "time": "created_at"},
            {},
        ),
    ]
    # Every business that sells: the old panels named the three sectors Sales sold in, which were all of them.
    assert all(not panel.verticals and panel.component is None for panel in panels)


def test_the_panels_are_titled_in_english_and_in_spanish_as_the_old_ones():
    with translation.override("en"):
        english = [str(panel.title) for panel in sale().widgets]
    with translation.override("es"):
        spanish = [str(panel.title) for panel in sale().widgets]
    assert english == [
        "Today's sales",
        "Today's tickets",
        "Sales, last 7 days",
        "Recent activity",
    ]
    assert spanish == [
        "Ventas hoy",
        "Tickets hoy",
        "Ventas últimos 7 días",
        "Actividad reciente",
    ]


def test_each_panel_is_refreshed_by_the_events_that_re_run_its_query():
    """The figures move with a charge, a void or a refund; the activity also with what changes a sale's row (its
    customer's card merged into another, the invoice that gives it its number): what live.py re-runs each on."""
    panels = {panel.key: panel for panel in sale().widgets}
    assert {key: list(panel.refresh_on) for key, panel in panels.items()} == {
        "today": FIGURES,
        "tickets_today": FIGURES,
        "last_7_days": FIGURES,
        "recent_activity": SALES,
    }
    for panel in panels.values():
        assert live_registry.is_subscribable(panel.operation), panel.key
        assert set(panel.refresh_on) == set(
            live_registry.subscribable[panel.operation]
        ), panel.key


def test_the_panels_icons_are_registered_in_the_shell():
    # Registered icons only (an unregistered one paints nothing): the old `trending-up-outline` and
    # `bar-chart-outline` wait in UI-REQUESTS.md.
    assert [panel.icon for panel in sale().widgets] == [
        "ion:cash-outline",
        "ion:receipt-outline",
        "ion:calendar-outline",
        "ion:time-outline",
    ]
    icons = (Path(settings.BASE_DIR) / "packages/ui/src/shell/icons.ts").read_text()
    for panel in sale().widgets:
        assert f"'{panel.icon.removeprefix('ion:')}'" in icons, panel.icon


def test_sales_has_no_setup_steps_nor_bell_counters():
    # The old module declared neither: its module.json has no `setup`, and the old hub's setup_status.rs only
    # listed the core's own steps (apps, business details, printer, team).
    assert (sale().setup, sale().bell) == ([], [])
