"""The cart_checkout app: an internal notebook of carts (of a person or of an anonymous session code)
and the orders made from them, with their number of the day and a payment status a person marks
(WORKBOOK.md). It is not the till and nothing it does is fiscal: the till is the sale app."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class CartCheckoutConfig(LiveAppConfig):
    name = "apps.cart_checkout"
    label = "cart_checkout"
    kind = "app"
    verbose_name = _("Cart & Checkout")
    icon = "lucide:shopping-bag"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "An internal notebook of shopping carts and the orders made from them, with a payment status you mark."
    )
    description = _(
        "Cart & Checkout keeps shopping carts, of a customer or of an anonymous session code, with their "
        "lines and totals, and turns them into orders with their own number of the day, addresses and "
        "shipping and payment methods. You mark each order as paid, failed or completed after charging "
        "it some other way. It is not the till and nothing in it is fiscal: it charges nothing and creates "
        "no sale, invoice, VeriFactu record, cash movement or stock movement."
    )
    # In no template: the old catalogue left it out of the MVP; a business turns it on from the store.
    verticals = []
    # Nothing: products and prices are free text and the customer an email and a name, as in the old
    # module (WORKBOOK «Decisión»).
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "cart_checkout.view_cart",
        "cart_checkout.manage_cart",
        "cart_checkout.checkout",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). As in the old
    # module: the manager has all three; the employee only looks.
    role_permissions = {
        "hub_owner": ["cart_checkout.*"],
        "hub_admin": ["cart_checkout.*"],
        "hub_manager": ["cart_checkout.*"],
        "hub_employee": ["cart_checkout.view_cart"],
    }
    # CART_CHECKOUT-F07: the phase-2 worker expires the overdue carts on every hub as the system
    # (cron in UTC). Reading already shows them as expired.
    scheduled_tasks = [
        {
            "name": "expire_overdue_carts",
            "operation": "cart_checkout.cart.cleanup_expired",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (UI-REQUESTS.md).
    navigation = [
        Nav("carts", _("Carts"), "lucide:shopping-bag", "/cart_checkout/carts"),
        Nav("orders", _("Orders"), "ion:receipt-outline", "/cart_checkout/orders"),
    ]
