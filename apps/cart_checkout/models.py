"""Models of the cart_checkout app: carts, their lines, the orders made from them and the counter that
numbers the orders by day.

- ``Cart`` is a shopping cart of a person (email and name, free text: no link to Customers) or of an
  anonymous visit, told apart by its session code. Its totals (items and amount) are the sum of its
  lines, kept by services.py. Deleting it is logical (``deleted_at``): its orders keep pointing at it,
  and its code is unique only among the carts not deleted.
- ``CartItem`` is one line: a product named in free text (no link to Inventory), a quantity with three
  decimals and a unit price in the minor unit of the cart's currency, with its total.
- ``Order`` (the old module's checkout session) is an order made from a cart, with its number
  ``OS-YYYYMMDD-NNNN``, the cart's total copied when it was initiated and its status: initiated →
  paid or failed → completed. «Paid» is a mark a person sets; nothing here charges.
- ``OrderCounter`` holds the last number given on a business day; services.py raises it with
  ``UPDATE … RETURNING`` in the transaction of the order (never a sequence).

Phase 1 has no tenancy (like ``apps.demo``): phase 2 moves these tables to each hub's database.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
SESSION_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 254
NAME_MAX_LENGTH = 255
SKU_MAX_LENGTH = 128
METHOD_MAX_LENGTH = 128
ORDER_NUMBER_MAX_LENGTH = 32
REASON_MAX_LENGTH = 500
#: A quantity: up to 999 999 999 999.999 units, three decimals (as sale and inventory).
QUANTITY = {"max_digits": 15, "decimal_places": 3}


class CartStatus(models.TextChoices):
    """Where a cart is (``Cart.Status``); out here so the model's constraint can read it."""

    ACTIVE = "active", pgettext_lazy("cart status", "Active")
    ABANDONED = "abandoned", pgettext_lazy("cart status", "Abandoned")
    CONVERTED = "converted", pgettext_lazy("cart status", "Converted")
    EXPIRED = "expired", pgettext_lazy("cart status", "Expired")


class OrderStatus(models.TextChoices):
    """Where an order is (``Order.Status``)."""

    INITIATED = "initiated", pgettext_lazy("order status", "Initiated")
    PAID = "paid", pgettext_lazy("order status", "Paid")
    FAILED = "failed", pgettext_lazy("order status", "Failed")
    COMPLETED = "completed", pgettext_lazy("order status", "Completed")


class Audited(UUIDModel):
    """Who created and last changed a row, and when."""

    created_by = models.CharField(_("created by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    updated_by = models.CharField(_("changed by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class Cart(Audited):
    Status = CartStatus

    session_token = models.CharField(pgettext_lazy("cart", "session"), max_length=SESSION_MAX_LENGTH)
    customer_email = models.CharField(_("customer email"), max_length=EMAIL_MAX_LENGTH, blank=True)
    customer_name = models.CharField(_("customer name"), max_length=NAME_MAX_LENGTH, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    # The sum of the lines: their quantities, and their totals in the minor unit of ``currency``.
    total_items = models.DecimalField(_("items"), default=Decimal("0"), **QUANTITY)
    total_amount = models.BigIntegerField(_("total"), default=0)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)
    last_activity_at = models.DateTimeField(_("last activity"), null=True, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    abandon_reason = models.TextField(_("abandonment reason"), blank=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"], name="cc_cart_status_idx"),
            models.Index(fields=["customer_email"], name="cc_cart_email_idx"),
            models.Index(fields=["created_at"], name="cc_cart_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session_token"],
                condition=Q(deleted_at__isnull=True),
                name="cart_checkout_cart_session_unique",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CartStatus.values), name="cart_checkout_cart_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="cart_checkout_cart_total_not_negative"
            ),
            models.CheckConstraint(
                condition=Q(total_items__gte=0), name="cart_checkout_cart_items_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.session_token


class CartItem(Audited):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("cart")
    )
    product_ref = models.CharField(_("product reference"), max_length=NAME_MAX_LENGTH)
    product_name = models.CharField(_("product name"), max_length=NAME_MAX_LENGTH)
    sku = models.CharField(_("SKU"), max_length=SKU_MAX_LENGTH, blank=True)
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    # In the minor unit of the cart's currency: the price is the caller's, the total quantity × price.
    unit_price = models.BigIntegerField(_("unit price"))
    line_total = models.BigIntegerField(_("line total"))
    variant_attributes = models.JSONField(_("variant attributes"), default=dict, blank=True)

    class Meta:
        verbose_name = _("cart line")
        verbose_name_plural = _("cart lines")
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="cart_checkout_item_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="cart_checkout_item_price_not_negative"
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0), name="cart_checkout_item_total_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_name} × {self.quantity:.3f}"


class Order(Audited):
    Status = OrderStatus

    cart = models.ForeignKey(
        Cart, on_delete=models.PROTECT, related_name="orders", verbose_name=_("cart")
    )
    order_number = models.CharField(
        _("order number"), max_length=ORDER_NUMBER_MAX_LENGTH, unique=True
    )
    # Empty once the customer's personal data was erased (CART_CHECKOUT-F14).
    customer_email = models.CharField(_("customer email"), max_length=EMAIL_MAX_LENGTH, blank=True)
    # Free fields (line1, city, postal_code, country…), as the old module kept them.
    shipping_address = models.JSONField(_("shipping address"), default=dict, blank=True)
    billing_address = models.JSONField(_("billing address"), default=dict, blank=True)
    shipping_method = models.CharField(_("shipping method"), max_length=METHOD_MAX_LENGTH, blank=True)
    payment_method = models.CharField(_("payment method"), max_length=METHOD_MAX_LENGTH, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.INITIATED
    )
    # The cart's total when the order was initiated, in the minor unit of ``currency``.
    total_amount = models.BigIntegerField(_("total"), default=0)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    notes = models.TextField(_("notes"), blank=True)
    failure_reason = models.TextField(_("failure reason"), blank=True)
    placed_at = models.DateTimeField(_("placed at"), null=True, blank=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    failed_at = models.DateTimeField(_("failed at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status"], name="cc_order_status_idx"),
            models.Index(fields=["customer_email"], name="cc_order_email_idx"),
            models.Index(fields=["created_at"], name="cc_order_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=OrderStatus.values), name="cart_checkout_order_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="cart_checkout_order_total_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return self.order_number


class OrderCounter(UUIDModel):
    """The last order number given on a business day."""

    day = models.DateField(_("business day"), unique=True)
    last = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("order counter")
        verbose_name_plural = _("order counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {self.last}"
