"""Django admin of the cart_checkout app: full CRUD over its tables, for the platform's staff only.

Round 12 (PLAN §17; CLAUDE.md «Frontend y admin»): the Hub's admin lives only on hubs.erplora.com and has
full CRUD over every table. A cart's lines are edited inside the cart. The database still refuses an
unknown status, negative totals, a repeated live session code and a repeated order number; the rules
(totals, steps of an order) and their events are the operations' (services.py), which the screens, the
API and the assistant use.
"""

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import get

from apps.cart_checkout.models import OWN, Cart, CartItem, Order, OrderCounter
from base.admin import ADMIN_HUB_SESSION_KEY

#: Set by the database or the model: shown, never typed.
AUDIT = ("id", "created_at", "updated_at")
ERASE = _("Erase the personal data of their customers")
ERASED = _("%(email)s: personal data erased from %(carts)s cart(s) and %(orders)s order(s).")
CHOOSE_A_HUB = pgettext_lazy(OWN, "Choose a hub first (its link in the SaaS admin): the action runs on that hub.")


def _staff_context(request) -> OperationContext | None:
    """The staff member on the hub chosen in the admin, allowed only what the action runs."""
    slug = request.session.get(ADMIN_HUB_SESSION_KEY)
    if not slug:
        return None
    return OperationContext(
        scope=Scope("host", slug),
        actor=request.user,
        permissions=frozenset({"cart_checkout.manage_cart"}),
        language=getattr(request, "LANGUAGE_CODE", "en"),
        request=request,
    )


class EraseCustomerData:
    """CART_CHECKOUT-F14 from the admin: ``cart_checkout.customer.erase`` once per customer email of the
    selected rows (rows without an email are skipped)."""

    actions = ["erase_customer_data"]

    @admin.action(description=ERASE)
    def erase_customer_data(self, request, queryset) -> None:
        ctx = _staff_context(request)
        if ctx is None:
            self.message_user(request, str(CHOOSE_A_HUB), messages.ERROR)
            return
        op = get("cart_checkout.customer.erase")
        emails = sorted({row.customer_email.lower() for row in queryset if row.customer_email})
        for email in emails:
            try:
                done = op(ctx, op.input.model_validate({"email": email}))
            except OperationError as refusal:
                self.message_user(request, f"{email}: {refusal.message}", messages.WARNING)
            else:
                said = str(ERASED) % {"email": email, "carts": done.carts, "orders": done.orders}
                self.message_user(request, said, messages.SUCCESS)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = (
        "product_ref",
        "product_name",
        "sku",
        "quantity",
        "unit_price",
        "line_total",
        "variant_attributes",
    )


@admin.register(Cart)
class CartAdmin(EraseCustomerData, admin.ModelAdmin):
    list_display = (
        "session_token",
        "customer_email",
        "customer_name",
        "status",
        "total_items",
        "total_amount",
        "currency",
        "deleted_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("session_token", "customer_email", "customer_name")
    readonly_fields = AUDIT
    inlines = [CartItemInline]
    fields = (
        "id",
        "session_token",
        "customer_email",
        "customer_name",
        "status",
        "total_items",
        "total_amount",
        "currency",
        "expires_at",
        "last_activity_at",
        "notes",
        "abandon_reason",
        "deleted_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )


@admin.register(Order)
class OrderAdmin(EraseCustomerData, admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer_email",
        "status",
        "payment_method",
        "total_amount",
        "currency",
        "placed_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("order_number", "customer_email")
    list_select_related = ("cart",)
    raw_id_fields = ("cart",)
    readonly_fields = AUDIT
    fields = (
        "id",
        "order_number",
        "cart",
        "customer_email",
        "shipping_address",
        "billing_address",
        "shipping_method",
        "payment_method",
        "status",
        "total_amount",
        "currency",
        "notes",
        "failure_reason",
        "placed_at",
        "paid_at",
        "failed_at",
        "completed_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )


@admin.register(OrderCounter)
class OrderCounterAdmin(admin.ModelAdmin):
    list_display = ("day", "last")
    readonly_fields = ("id",)
    fields = ("id", "day", "last")
