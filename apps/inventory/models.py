"""Models of the inventory app: products, their categories, the stock ledger, the settings and the sales seen.

Money is in cents (integers, never negative). Quantities are exact decimals with three places, the
finest step of any unit (a gram in a kilo); each unit has its own step (``UNIT_SPECS``) and a
quantity off it is refused, never rounded. Products and categories are deleted logically: the ledger
keeps pointing at them. Phase 1 has no tenancy: every scope shares these tables; phase 2 moves them
to each hub's database.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

QUANTITY = {"max_digits": 15, "decimal_places": 3}
ACTOR_MAX_LENGTH = 128
DEFAULT_CATEGORY_ICON = "ion:cube-outline"
DEFAULT_CATEGORY_COLOR = "#3880ff"


class Unit(models.TextChoices):
    """The eight units of measure every business gets; none is ever added."""

    UNIT = "ud", _("Unit (ud)")
    KILOGRAM = "kg", _("Kilogram (kg)")
    GRAM = "g", _("Gram (g)")
    TONNE = "t", _("Tonne (t)")
    LITRE = "l", _("Litre (l)")
    MILLILITRE = "ml", _("Millilitre (ml)")
    MINUTE = "min", _("Minute (min)")
    HOUR = "h", _("Hour (h)")


@dataclass(frozen=True)
class UnitSpec:
    category: str
    # Exact fraction towards the reference unit of its category: 1 min = 1/60 h has no finite decimal.
    factor: Fraction
    # The step every quantity in this unit is a multiple of (independent of the three decimals).
    increment: Decimal
    is_reference: bool = False


UNIT_SPECS: dict[str, UnitSpec] = {
    Unit.UNIT: UnitSpec("count", Fraction(1), Decimal("1"), is_reference=True),
    Unit.KILOGRAM: UnitSpec("mass", Fraction(1), Decimal("0.001"), is_reference=True),
    Unit.GRAM: UnitSpec("mass", Fraction(1, 1000), Decimal("1")),
    Unit.TONNE: UnitSpec("mass", Fraction(1000), Decimal("0.001")),
    Unit.LITRE: UnitSpec("volume", Fraction(1), Decimal("0.001"), is_reference=True),
    Unit.MILLILITRE: UnitSpec("volume", Fraction(1, 1000), Decimal("1")),
    Unit.MINUTE: UnitSpec("time", Fraction(1), Decimal("1"), is_reference=True),
    Unit.HOUR: UnitSpec("time", Fraction(60), Decimal("0.25")),
}


def increment_of(unit: str) -> Decimal:
    return UNIT_SPECS[unit].increment


def fits_unit(qty: Decimal, unit: str) -> bool:
    """Whether ``qty`` is a multiple of the step of ``unit`` (a negative balance included)."""
    return qty % increment_of(unit) == 0


class Settings(UUIDModel):
    """The business's inventory settings: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    allow_sell_without_stock = models.BooleanField(
        _("allow selling without stock"), default=False
    )
    # In whole units: what a product created without its own threshold is born with.
    low_stock_threshold = models.PositiveIntegerField(
        _("low stock threshold"), default=10
    )
    track_stock = models.BooleanField(_("track stock"), default=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("inventory settings")
        verbose_name_plural = _("inventory settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="inventory_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="inventory_settings_singleton"
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class Category(UUIDModel):
    """A group of products for the till and the kitchen; deleted logically, never deactivated."""

    name = models.CharField(_("name"), max_length=100)
    slug = models.CharField(_("slug"), max_length=120, blank=True)
    description = models.TextField(_("description"), blank=True)
    # The old module's defaults, which the till's category strip paints.
    icon = models.CharField(_("icon"), max_length=64, blank=True, default=DEFAULT_CATEGORY_ICON)
    color = models.CharField(_("color"), max_length=7, blank=True, default=DEFAULT_CATEGORY_COLOR)
    order = models.PositiveIntegerField(_("order"), default=0)
    # Optional for a category; tax.TaxCategory is a ``requires`` and is never deleted.
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("tax category"),
    )
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["name", "id"], name="inventory_category_name_idx")
        ]

    def __str__(self) -> str:
        return self.name


class Product(UUIDModel):
    """An article of the catalog; its stock moves only through the ledger (StockMovement)."""

    class Type(models.TextChoices):
        PHYSICAL = "physical", _("Physical")
        SERVICE = "service", _("Service")

    name = models.CharField(_("name"), max_length=200)
    sku = models.CharField(_("SKU"), max_length=64)
    ean13 = models.CharField(_("EAN-13"), max_length=13, null=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    product_type = models.CharField(
        _("type"), max_length=16, choices=Type.choices, default=Type.PHYSICAL
    )
    price = models.PositiveBigIntegerField(_("price"))
    cost = models.PositiveBigIntegerField(_("cost"), default=0)
    stock = models.DecimalField(_("stock"), default=Decimal("0"), **QUANTITY)
    low_stock_threshold = models.DecimalField(
        _("low stock threshold"), default=Decimal("10"), **QUANTITY
    )
    unit = models.CharField(
        _("unit of measure"), max_length=8, choices=Unit.choices, default=Unit.UNIT
    )
    # The price is per this quantity of pricing_unit: «0.37 € per 100 ud».
    price_quantity = models.DecimalField(
        _("price quantity"), default=Decimal("1"), **QUANTITY
    )
    pricing_unit = models.CharField(
        _("pricing unit"), max_length=8, choices=Unit.choices, default=Unit.UNIT
    )
    # Without it the product cannot be sold (it needs tax setup); tax.TaxCategory is never deleted.
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("tax category"),
    )
    # None = follows the business's «Track stock» setting.
    track_stock = models.BooleanField(_("track stock"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    # Sold out («86»): still active, but the till does not offer it until it is back on sale.
    # ``db_default``: a process still on the previous code inserts products without it (expand/contract).
    is_sold_out = models.BooleanField(_("sold out"), default=False, db_default=False)
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    categories = models.ManyToManyField(
        Category,
        through="ProductCategory",
        related_name="products",
        verbose_name=_("categories"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["name", "id"], name="inventory_product_name_idx"),
            models.Index(
                fields=["is_deleted", "is_active"], name="inventory_product_live_idx"
            ),
        ]
        constraints = [
            # A deleted product frees its codes for a new one.
            models.UniqueConstraint(
                fields=["sku"],
                condition=Q(is_deleted=False),
                name="inventory_product_live_sku_unique",
            ),
            models.UniqueConstraint(
                fields=["ean13"],
                condition=Q(is_deleted=False, ean13__isnull=False),
                name="inventory_product_live_ean13_unique",
            ),
            models.CheckConstraint(
                condition=Q(price_quantity__gt=0),
                name="inventory_product_price_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(low_stock_threshold__gte=0),
                name="inventory_product_threshold_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class ProductCategory(UUIDModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="category_links",
        verbose_name=_("product"),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="product_links",
        verbose_name=_("category"),
    )

    class Meta:
        verbose_name = _("product category")
        verbose_name_plural = _("product categories")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "category"], name="inventory_product_category_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} → {self.category_id}"


class StockMovement(UUIDModel):
    """One change of a product's balance: never edited, never deleted; the balance is explained by them."""

    class Type(models.TextChoices):
        INITIAL = "initial", _("Initial")
        RECEPTION = "reception", _("Reception")
        SALE = "sale", _("Sale")
        VOID = "void", _("Void")
        COUNT = "count", _("Count")
        WRITE_OFF = "write_off", _("Write-off")
        REFUND = "refund", _("Refund")

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name=_("product"),
    )
    movement_type = models.CharField(_("type"), max_length=16, choices=Type.choices)
    # Signed: what the balance changed by.
    qty = models.DecimalField(_("quantity"), **QUANTITY)
    stock_after = models.DecimalField(_("balance"), **QUANTITY)
    reason = models.CharField(_("reason"), max_length=500, blank=True)
    # The sale (sale, void and refund) or the delivery note (reception).
    reference = models.CharField(_("reference"), max_length=200, blank=True)
    unit_cost = models.PositiveBigIntegerField(_("unit cost"), null=True, blank=True)
    actor = models.CharField(_("by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(_("date"), default=timezone.now)

    class Meta:
        verbose_name = _("stock movement")
        verbose_name_plural = _("stock movements")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["-created_at", "-id"], name="inventory_movement_recent_idx"
            ),
            models.Index(
                fields=["product", "-created_at"], name="inventory_movement_product_idx"
            ),
            models.Index(
                fields=["reference", "movement_type"], name="inventory_movement_ref_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(qty=0), name="inventory_movement_qty_not_zero"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.qty} ({self.product_id})"


class SaleStock(UUIDModel):
    """What inventory did with a sale of the Sales app: its stock is lowered once and restored once."""

    class State(models.TextChoices):
        MOVED = "moved", _("Lowered the stock")
        UNMOVED = "unmoved", _("Moved nothing")
        VOIDED = "voided", _("Voided")

    sale_id = models.UUIDField(_("sale"))
    state = models.CharField(_("state"), max_length=8, choices=State.choices)
    # INVENTORY-F16: the numbers a person knows the sale by, kept when its stock moves, so the ledger shows
    # and finds them. The sale's own number, and the number of its ticket or invoice when it has one.
    sale_number = models.CharField(_("sale number"), max_length=24, blank=True, default="", db_default="")
    document_number = models.CharField(
        _("ticket or invoice number"), max_length=64, blank=True, default="", db_default=""
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("sale seen")
        verbose_name_plural = _("sales seen")
        constraints = [
            models.UniqueConstraint(
                fields=["sale_id"], name="inventory_sale_stock_sale_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.sale_id} ({self.state})"


class RefundStock(UUIDModel):
    """A refund of the Sales app that inventory already applied: its units go back to the stock once."""

    refund_id = models.UUIDField(_("refund"))
    sale_id = models.UUIDField(_("sale"))
    movements = models.PositiveIntegerField(_("movements"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("refund seen")
        verbose_name_plural = _("refunds seen")
        constraints = [
            models.UniqueConstraint(
                fields=["refund_id"], name="inventory_refund_stock_refund_unique"
            )
        ]

    def __str__(self) -> str:
        return f"{self.refund_id} ({self.movements})"
