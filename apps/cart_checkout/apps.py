"""The cart_checkout app: an internal notebook of carts (of a person or of an anonymous session code)
and the orders made from them, with their number of the day and a payment status a person marks
(WORKBOOK.md). It is not the till and nothing it does is fiscal: the till is the sale app."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). A «cesta» or a «carrito» is a shopping
    # cart (cart_checkout.cart), and «unidades» or «cantidad», as «tres unidades», the quantity a line takes (never
    # «cantidad» as Inventory's unit of measure). Never «línea»: it is the till's check line (sale.order.*_line) and a
    # cart's line would take its place.
    assistant_synonyms = (
        ("unidades", "cantidad", "quantity"),
        ("cesta", "carrito", "cart", "basket"),
    )
    permissions = {
        "cart_checkout.view_cart": _("View carts, their lines and orders"),
        "cart_checkout.manage_cart": _("Create, change and empty carts, and erase a customer's personal data"),
        "cart_checkout.checkout": _("Start orders and mark them paid, failed or completed"),
    }
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
        Nav("carts", _("Carts"), "lucide:shopping-bag", "/cart_checkout/carts", permission="cart_checkout.view_cart"),
        Nav(
            "orders", _("Orders"), "ion:receipt-outline", "/cart_checkout/orders",
            permission="cart_checkout.view_cart",
        ),
    ]
    help = Help(
        videos={"es": "BsQdeNv70R0", "en": "xjvkg4GVStE"},
        flow_videos={
            "CART_CHECKOUT-F01": {"es": ["kx8RsQwjKB8"], "en": ["WKCQruONKUI"]},
            "CART_CHECKOUT-F05": {"es": ["kx8RsQwjKB8"], "en": ["WKCQruONKUI"]},
            "CART_CHECKOUT-F06": {"es": ["kx8RsQwjKB8"], "en": ["WKCQruONKUI"]},
        },
    )

    fiscal_archive_models = ("Cart", "CartItem", "Order")

    def fiscal_documents_kept(self) -> bool:
        """The platform asks (``base.tenancy.offboarding``) before it drops the database of a business that left: its
        shop orders (no sale backs them: «paid» is a mark) are documents to keep, so the database stays; they go to the
        fiscal archive first (``fiscal_archive_models``)."""
        from apps.cart_checkout import queries  # the models are not loaded yet when this module is

        return queries.keeps_fiscal_documents()
