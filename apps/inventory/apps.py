"""The inventory app: the catalog of what is sold with stock, its categories and the stock ledger."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


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
