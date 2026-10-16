"""The sale app: the till (open checks and their lines), the immutable sales it charges, their voids and
refunds, the payment methods, the departments of the open price, the quick notes and the till settings
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class SaleConfig(LiveAppConfig):
    name = "apps.sale"
    label = "sale"
    kind = "app"
    verbose_name = _("Sales & POS")
    icon = "ion:cart-outline"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "The till: build the check, charge it in cash, by card or split, and void or refund a sale."
    )
    description = _(
        "Sales & POS is the business's cash register. Build the check by tapping articles or typing an "
        "open price by section, add notes, discounts and comps, park it and pick it up again, charge "
        "it whole or in parts, in cash with change, by card or split between several methods, as a "
        "ticket or a full invoice. Every sale gets its number of the day and its VAT line by line, is "
        "never edited, and is corrected by voiding it or refunding it, whole or in part. Inventory "
        "lowers the stock and Customers adds the purchase on their own."
    )
    verticals = ["hair_salon", "restaurant"]
    # Every line is priced with tax's rules and a sale keeps its customer's card (foreign keys).
    # Inventory is optional (PLAN §20.5): its products are read through its own operations.
    requires = ["tax", "customer"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
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
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # (an employee who also charges) is the employee now.
    role_permissions = {
        "hub_owner": ["sale.*"],
        "hub_admin": ["sale.*"],
        "hub_manager": ["sale.*"],
        "hub_employee": [
            "sale.view_sale",
            "sale.add_sale",
            "sale.take_payment",
            "sale.view_paymentmethod",
        ],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only: the old `storefront` (filled) and
    # `chatbubble-ellipses-outline` wait in UI-REQUESTS.md. The departments of the open price read
    # «Sections»: the old «Departments» was one word wider than a fifth of a phone's tabbar.
    navigation = [
        Nav("pos", _("Sell"), "ion:storefront-outline", "/sale/pos"),
        Nav("sales", _("Sales"), "ion:cart-outline", "/sale/sales"),
        Nav(
            "quick_notes",
            _("Quick notes"),
            "ion:chatbubbles-outline",
            "/sale/quick-notes",
        ),
        Nav("departments", _("Sections"), "ion:grid-outline", "/sale/departments"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/sale/settings"),
    ]
