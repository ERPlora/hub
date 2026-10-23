"""The inventory app: the catalog of what is sold with stock, its categories and the stock ledger."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep, Widget

from apps.inventory.events import FIGURE_EVENTS, PRODUCT_EVENTS

VIEW = "inventory.view_product"


class InventoryConfig(LiveAppConfig):
    name = "apps.inventory"
    label = "inventory"
    kind = "app"
    verbose_name = _("Inventory")
    icon = "ion:cube-outline"
    category = Category.CATALOG
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your catalog with its stock: products, categories, goods received, counts and low-stock alerts."
    )
    description = _(
        "Inventory keeps what you sell with stock: each product with its SKU, price, cost, tax category, "
        "unit of measure and how many are left. The till sells from this catalog and every sale lowers "
        "the stock on its own; goods received, stock counts and write-offs leave a movement that is never "
        "edited, so every balance is explained. It warns when an article runs low, imports and exports "
        "the catalog as CSV and sells by weight or measure without rounding."
    )
    # The restaurant's menu is this catalog; the hair salon's template does not carry it (PLAN-HUB §7).
    verticals = ["restaurant"]
    # Each product and category points at a tax category (tax.TaxCategory).
    requires = ["tax"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
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
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old
    # ``cashier`` role is gone: it had exactly what the employee has.
    role_permissions = {
        "hub_owner": ["inventory.*"],
        "hub_admin": ["inventory.*"],
        "hub_manager": ["inventory.*"],
        "hub_employee": [
            "inventory.view_product",
            "inventory.view_category",
            "inventory.view_stock",
        ],
    }
    navigation = [
        Nav(
            id="inventory",
            label=_("Inventory"),
            icon="ion:cube-outline",
            path="/inventory",
        )
    ]
    # The Home's hooks (PLAN-HUB round 2026-10-21): the old module's `setup` and `widgets` (it had no `bell`), on the
    # Panel's own queries. Registered icons only: the old `trending-down-outline` waits in UI-REQUESTS.md.
    setup = [
        SetupStep(
            key="catalog",
            operation="inventory.stock.get_summary",
            configured_when=[SetupCheck(field="active_products", truthy=True)],
            title=_("Your catalog"),
            description=_("Add at least one product so there is something to sell."),
            icon="ion:cube-outline",
            route="/inventory/products",
            permission="inventory.add_product",
            order=30,
            required=True,
            refresh_on=PRODUCT_EVENTS,
        )
    ]
    widgets = [
        # A KPI says its name once, in its title (gh:hub#1105); the money one in the hub's currency (gh:inventory#123).
        Widget(
            key="low_stock_count",
            title=_("Low-stock products"),
            icon="ion:alert-circle-outline",
            size="sm",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="inventory.stock.get_summary",
            map={"value": "products_low_stock"},
            options={"format": "number"},
        ),
        Widget(
            key="value",
            title=_("Stock value (at cost)"),
            icon="ion:cash-outline",
            size="sm",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="inventory.stock.get_summary",
            map={"value": "stock_value"},
            options={"format": "currency"},
        ),
        Widget(
            key="in_stock",
            title=_("Products in stock"),
            icon="ion:cube-outline",
            size="sm",
            permission=VIEW,
            refresh_on=FIGURE_EVENTS,
            kind="stat",
            operation="inventory.stock.get_summary",
            map={"value": "products_in_stock"},
            options={"format": "number"},
        ),
        # The Panel's own page size: the five with less stock, the one with less first.
        Widget(
            key="low_stock_products",
            title=_("Lowest-stock products"),
            icon="ion:arrow-down-outline",
            size="md",
            permission=VIEW,
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="bar-list",
            operation="inventory.product.list_low_stock",
            params={"limit": 5},
            map={"label": "name", "value": "stock"},
            options={"valueFormat": "number"},
        ),
    ]
