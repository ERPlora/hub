"""Models of the pricing app: price lists, their prices, and the automatic discount rules of a line.

- ``PriceList`` is a set of prices other than the catalog's: for a customer group (or for everybody,
  the general one), between two dates. Its code is unique whatever its case; at most one is general.
- ``PriceItem`` is the price of a product of Inventory or a service of Services in a list, from a
  minimum quantity on (quantity breaks: the same article again with another minimum).
- ``DiscountRule`` takes an amount off a line: a percent, an amount per unit, buy X get Y, or a
  percent by quantity tiers; limited to a scope, a customer group, a minimum quantity and dates.

Money is in cents; quantities are exact decimals with three places, as Inventory's. A service is an
opaque id with a copy of its name: Services is no requirement (WORKBOOK). A customer group is an
opaque id too, read from Customers' model: Customers deletes a group for real, and a foreign key would
make that deletion read these tables, which a hub without Pricing does not have (the reaction to
``customer.group.deleted`` tidies up, events.py). Products and categories are only ever deleted
logically by Inventory: their foreign keys cascade only when the platform's staff deletes a row in the
admin. Phase 1 has no tenancy: every scope shares these tables; phase 2 moves them to each hub's
database.
"""

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

QUANTITY = {"max_digits": 15, "decimal_places": 3}
ACTOR_MAX_LENGTH = 128
CODE_MAX_LENGTH = 50
NAME_MAX_LENGTH = 200
DEFAULT_PRIORITY = 100

_VALID_RANGE = Q(valid_from__isnull=True) | Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from"))


class _Audited(UUIDModel):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(_("created by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    updated_by = models.CharField(_("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        abstract = True


class PriceList(_Audited):
    code = models.CharField(_("code"), max_length=CODE_MAX_LENGTH)
    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    # ISO 4217, two decimals (the amounts are typed and read in cents).
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    # Whether its prices carry the tax: empty = as the business sells (Sales' setting).
    tax_included = models.BooleanField(_("tax included"), null=True, blank=True)
    # A customer.CustomerGroup; empty: nobody's group (the general list, or a list asked for by name).
    customer_group_id = models.UUIDField(_("customer group"), null=True, blank=True)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    is_default = models.BooleanField(_("general list"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("price list")
        verbose_name_plural = _("price lists")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("code"), name="pricing_price_list_code_unique"),
            models.UniqueConstraint(
                fields=["is_default"], condition=Q(is_default=True), name="pricing_price_list_one_default"
            ),
            models.CheckConstraint(
                condition=~Q(is_default=True) | Q(customer_group_id__isnull=True, is_active=True),
                name="pricing_price_list_default_for_everybody",
            ),
            models.CheckConstraint(condition=_VALID_RANGE, name="pricing_price_list_valid_range"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class PriceItem(_Audited):
    price_list = models.ForeignKey(
        PriceList, on_delete=models.CASCADE, related_name="items", verbose_name=_("price list")
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("product"),
    )
    service_id = models.UUIDField(_("service"), null=True, blank=True)
    # A copy of the service's name, kept fresh by service.service.updated (events.py).
    service_name = models.CharField(_("service name"), max_length=NAME_MAX_LENGTH, blank=True)
    # Cents, for the same quantity the catalog's price is for (price_quantity of pricing_unit).
    price = models.PositiveBigIntegerField(_("price"))
    # In the product's own unit (a service: units).
    min_quantity = models.DecimalField(_("from quantity"), default=1, **QUANTITY)

    class Meta:
        verbose_name = _("price")
        verbose_name_plural = _("prices")
        ordering = ["price_list", "min_quantity", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(product__isnull=False, service_id__isnull=True)
                | Q(product__isnull=True, service_id__isnull=False),
                name="pricing_price_item_one_target",
            ),
            models.CheckConstraint(condition=Q(min_quantity__gt=0), name="pricing_price_item_quantity_positive"),
            models.UniqueConstraint(
                fields=["price_list", "product", "min_quantity"],
                condition=Q(product__isnull=False),
                name="pricing_price_item_product_unique",
            ),
            models.UniqueConstraint(
                fields=["price_list", "service_id", "min_quantity"],
                condition=Q(service_id__isnull=False),
                name="pricing_price_item_service_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.price_list_id}: {self.product_id or self.service_name} ≥ {self.min_quantity}"


class DiscountRule(_Audited):
    class Type(models.TextChoices):
        PERCENT = "percent", _("Percentage")
        FIXED = "fixed", _("Amount per unit")
        BUY_X_GET_Y = "buy_x_get_y", _("Buy X, get Y")
        TIERED = "tiered", _("Tiered")

    class Scope(models.TextChoices):
        ALL = "all", _("Everything")
        PRODUCTS = "products", _("All products")
        SERVICES = "services", _("All services")
        CATEGORY = "category", _("A category")
        PRODUCT = "product", _("A product")
        SERVICE = "service", _("A service")

    code = models.CharField(_("code"), max_length=CODE_MAX_LENGTH)
    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    rule_type = models.CharField(_("type"), max_length=16, choices=Type.choices, default=Type.PERCENT)
    # A rate, not money (percent).
    percent = models.DecimalField(_("percent"), max_digits=5, decimal_places=2, null=True, blank=True)
    # Cents off each unit sold (fixed).
    amount = models.PositiveBigIntegerField(_("amount per unit"), null=True, blank=True)
    buy_quantity = models.PositiveIntegerField(_("buy"), null=True, blank=True)
    get_quantity = models.PositiveIntegerField(_("free"), null=True, blank=True)
    # ``[{"min_quantity": "3", "percent": "10"}]`` by rising quantity (tiered); validated by schemas.py.
    tiers = models.JSONField(_("tiers"), default=list, blank=True)
    applies_to = models.CharField(_("applies to"), max_length=16, choices=Scope.choices, default=Scope.ALL)
    category = models.ForeignKey(
        "inventory.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("category"),
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("product"),
    )
    service_id = models.UUIDField(_("service"), null=True, blank=True)
    service_name = models.CharField(_("service name"), max_length=NAME_MAX_LENGTH, blank=True)
    # A customer.CustomerGroup; empty: every customer (a sale without customer too). A deleted group
    # switches its rules off and keeps the id: never would a VIP discount spread to everybody.
    customer_group_id = models.UUIDField(_("customer group"), null=True, blank=True)
    min_quantity = models.DecimalField(_("minimum quantity"), null=True, blank=True, **QUANTITY)
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    # With equal discounts, the lower number wins.
    priority = models.PositiveIntegerField(_("priority"), default=DEFAULT_PRIORITY)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("discount rule")
        verbose_name_plural = _("discount rules")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("code"), name="pricing_rule_code_unique"),
            models.CheckConstraint(condition=_VALID_RANGE, name="pricing_rule_valid_range"),
            models.CheckConstraint(
                condition=~Q(rule_type="percent") | Q(percent__isnull=False, percent__gt=0, percent__lte=100),
                name="pricing_rule_percent_value",
            ),
            models.CheckConstraint(
                condition=~Q(rule_type="fixed") | Q(amount__isnull=False, amount__gt=0), name="pricing_rule_fixed_value"
            ),
            models.CheckConstraint(
                condition=~Q(rule_type="buy_x_get_y") | Q(buy_quantity__isnull=False, buy_quantity__gt=0, get_quantity__isnull=False, get_quantity__gt=0),
                name="pricing_rule_buy_x_get_y_value",
            ),
            models.CheckConstraint(
                condition=~Q(rule_type="tiered") | ~Q(tiers=[]), name="pricing_rule_tiered_value"
            ),
            models.CheckConstraint(
                condition=Q(category__isnull=True) | Q(applies_to="category"), name="pricing_rule_category_scope"
            ),
            models.CheckConstraint(
                condition=~Q(applies_to="category") | Q(category__isnull=False), name="pricing_rule_category_set"
            ),
            models.CheckConstraint(
                condition=Q(product__isnull=True) | Q(applies_to="product"), name="pricing_rule_product_scope"
            ),
            models.CheckConstraint(
                condition=~Q(applies_to="product") | Q(product__isnull=False), name="pricing_rule_product_set"
            ),
            models.CheckConstraint(
                condition=Q(service_id__isnull=True) | Q(applies_to="service"), name="pricing_rule_service_scope"
            ),
            models.CheckConstraint(
                condition=~Q(applies_to="service") | Q(service_id__isnull=False), name="pricing_rule_service_set"
            ),
            models.CheckConstraint(
                condition=Q(min_quantity__isnull=True) | Q(min_quantity__gt=0),
                name="pricing_rule_min_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"
