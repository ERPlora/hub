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
    # The public store's texts, which register_apps writes to shared.app.
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
    # In no template: a business turns it on from the store.
    verticals = []
    # Nothing: products and prices are free text and the customer an email and a name (WORKBOOK «Decisión»).
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "cart_checkout.view_cart",
        "cart_checkout.manage_cart",
        "cart_checkout.checkout",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The manager has all
    # three; the employee only looks.
    role_permissions = {
        "hub_owner": ["cart_checkout.*"],
        "hub_admin": ["cart_checkout.*"],
        "hub_manager": ["cart_checkout.*"],
        "hub_employee": ["cart_checkout.view_cart"],
    }
    # CART_CHECKOUT-F07: the Hub's worker (`base.scheduler`) expires the overdue carts as the system
    # every quarter of an hour (cron in UTC). Reading already shows them as expired.
    # `tests/test_scheduled_expiry.py` runs it without waiting for the clock.
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

    def fiscal_documents_kept(self) -> bool:
        """The platform asks (``base.tenancy.offboarding``) before it drops the database of a business that left:
        its shop orders (no sale backs them: «paid» is a mark) are documents nothing archives yet, so the database
        stays."""
        from apps.cart_checkout import queries  # the models are not loaded yet when this module is

        return queries.keeps_fiscal_documents()
