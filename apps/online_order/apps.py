"""Online orders: the customer at a table orders from their phone with the table's QR, and the order reaches the
table's check and the kitchen. Each table has its own code, the one its QR carries."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig


class OnlineOrderConfig(LiveAppConfig):
    name = "apps.online_order"
    label = "online_order"
    kind = "app"
    verbose_name = _("Online orders")
    icon = "ion:qr-code-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _("Let customers order from their table by scanning its QR, straight to the check and the kitchen.")
    description = _(
        "Online orders gives each table its own QR. The customer scans it with their phone, sees the menu and orders "
        "without an account or an app, and the order goes into the table's check and on to the kitchen; the first "
        "order of a table without a check waits for an employee to accept it. Payment stays at the POS. If a QR "
        "should stop working, regenerate it and print the new one."
    )
    # In no vertical's template: a restaurant turns it on itself when it wants its customers to order alone.
    verticals = []
    # Out of the store until it has a screen: a business that turned it on today would get nothing to use.
    listed = False
    # The tables (and, through them, Sales and Customers): it reads them by Tables' operations.
    requires = ["table"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = {
        "online_order.view_qr_code": _("See the tables' QR codes"),
        "online_order.change_qr_code": _("Regenerate the tables' QR codes"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["online_order.*"],
        "hub_admin": ["online_order.*"],
        "hub_manager": ["online_order.view_qr_code", "online_order.change_qr_code"],
        "hub_employee": [],
    }
    navigation = []
