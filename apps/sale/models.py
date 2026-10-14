"""Models of the sale app.

- ``Order`` is the open check (mutable): its ``OrderLine`` rows freeze the price, the unit and the tax
  category when the line is added; ``version`` goes up with every change, so a charge can tell that the
  check moved under it. An order ends ``completed`` (charged to the last line) or ``voided``.
- ``Sale`` is the fiscal record a charge creates (immutable but for its void and its refunds): number of
  the business day, amounts, document type, customer; ``SaleLine`` keeps the fiscal copy of each line
  (category, rate, country, region and rule of tax) and ``SalePayment`` each tender.
- ``SaleCounter`` numbers the sales of a business day (``UPDATE … RETURNING``, never a sequence).
- ``Refund`` (with ``RefundPayment`` and ``RefundLine``) gives money back by tender, and the lines that
  return with it.
- ``PaymentMethod``, ``Settings`` (one row), ``Department`` and ``QuickNote`` are the till's catalogues.

Money is in whole cents and never negative; quantities are exact decimals with three places. Inventory
is no requirement: a line keeps a copy of its product, whose id is a plain UUID.
"""

import datetime as dt
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

QUANTITY = {"max_digits": 15, "decimal_places": 3}
PERCENT = {"max_digits": 5, "decimal_places": 2}
ACTOR_MAX_LENGTH = 128
NUMBER_WIDTH = 4


def sale_number(day: dt.date, sequence: int) -> str:
    """``AAAAMMDD-NNNN``: four digits as a minimum width, never a ceiling (the 10.000th is ``-10000``)."""
    return f"{day:%Y%m%d}-{sequence:0{NUMBER_WIDTH}d}"


def _percent_range(
    name: str, field: str = "discount_percent"
) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=Q(**{f"{field}__gte": 0, f"{field}__lte": 100}), name=name
    )


class PaymentMethod(UUIDModel):
    class Type(models.TextChoices):
        CASH = "cash", _("Cash")
        CARD = "card", _("Card")
        TRANSFER = "transfer", _("Bank transfer")
        OTHER = "other", _("Other")

    name = models.CharField(_("name"), max_length=60)
    type = models.CharField(
        _("type"), max_length=16, choices=Type.choices, default=Type.CASH
    )
    # The factory ones (migration 0002) keep their English name and read in the reader's language.
    is_system = models.BooleanField(_("factory"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveIntegerField(_("position"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("payment method")
        verbose_name_plural = _("payment methods")
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name

    @property
    def display_name(self) -> str:
        """A factory method's name in the active language while it keeps its factory name."""
        label = FACTORY_METHOD_NAMES.get(self.name) if self.is_system else None
        return str(label) if label else self.name

    @property
    def requires_change(self) -> bool:
        """Cash asks what was handed over and gives change; the rest charge the exact amount."""
        return self.type == self.Type.CASH


#: The factory payment methods' names (migration 0002) → their translation.
FACTORY_METHOD_NAMES = {"Cash": _("Cash"), "Card": _("Card")}


class Settings(UUIDModel):
    """The till settings of the business: one row at most; without it, the factory values apply."""

    class DocumentType(models.TextChoices):
        TICKET = "ticket", _("Ticket")
        INVOICE = "invoice", _("Invoice")

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    allow_cash = models.BooleanField(_("allow cash"), default=True)
    allow_card = models.BooleanField(_("allow card"), default=True)
    allow_transfer = models.BooleanField(_("allow bank transfer"), default=False)
    show_products = models.BooleanField(_("show products in the till"), default=True)
    show_services = models.BooleanField(_("show services in the till"), default=True)
    require_customer = models.BooleanField(
        _("require a customer on every sale"), default=False
    )
    allow_discounts = models.BooleanField(_("allow discounts"), default=True)
    max_discount_percent = models.PositiveSmallIntegerField(
        _("maximum discount (%)"), default=100
    )
    enable_parked_tickets = models.BooleanField(_("allow parked checks"), default=True)
    default_tax_included = models.BooleanField(_("prices include VAT"), default=True)
    auto_invoice_with_tax_id = models.BooleanField(
        _("invoice when the customer has a tax ID"), default=False
    )
    default_document_type = models.CharField(
        _("default document"),
        max_length=8,
        choices=DocumentType.choices,
        default=DocumentType.TICKET,
    )
    receipt_header = models.TextField(_("receipt header"), blank=True)
    receipt_footer = models.TextField(_("receipt footer"), blank=True)
    receipt_footer_image = models.CharField(
        _("receipt footer image"), max_length=500, blank=True
    )
    receipt_marketing_url = models.CharField(
        _("promotional QR URL"), max_length=500, blank=True
    )
    receipt_marketing_text = models.CharField(
        _("promotional QR text"), max_length=200, blank=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("till settings")
        verbose_name_plural = _("till settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="sale_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="sale_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(max_discount_percent__lte=100),
                name="sale_settings_cap_range",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


class Department(UUIDModel):
    """A department of the open price: the name the cashier reads and the tax category it charges at."""

    name = models.CharField(_("name"), max_length=60)
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("tax category"),
    )
    sort_order = models.PositiveIntegerField(_("position"), default=0)
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("department")
        verbose_name_plural = _("departments")
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name


class QuickNote(UUIDModel):
    """A preset note the line-note sheet offers as a chip."""

    text = models.CharField(_("note"), max_length=80)
    sort_order = models.PositiveIntegerField(_("position"), default=0)
    is_deleted = models.BooleanField(_("deleted"), default=False)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("quick note")
        verbose_name_plural = _("quick notes")
        ordering = ["sort_order", "text", "id"]

    def __str__(self) -> str:
        return self.text


class Order(UUIDModel):
    """An open check: mutable, its amounts provisional; charging it creates one or more sales."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        COMPLETED = "completed", _("Completed")
        VOIDED = "voided", _("Voided")

    class Source(models.TextChoices):
        POS = "pos", _("Till")
        COUNTER = "counter", _("Counter sale")

    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.OPEN
    )
    source = models.CharField(
        _("source"), max_length=10, choices=Source.choices, default=Source.POS
    )
    label = models.CharField(_("title"), max_length=120, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    appointment_id = models.UUIDField(_("appointment"), null=True, blank=True)
    discount_percent = models.DecimalField(
        _("discount (%)"), default=Decimal("0"), **PERCENT
    )
    discount_amount = models.PositiveBigIntegerField(_("discount (cents)"), default=0)
    discount_approved_by = models.CharField(
        _("discount approved by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    # Σ of the live unpaid lines' totals, before the ticket discount: what the till paints, never fiscal.
    provisional_total = models.BigIntegerField(_("provisional total"), default=0)
    version = models.PositiveIntegerField(_("version"), default=1)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    voided_by = models.CharField(
        _("voided by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("open check")
        verbose_name_plural = _("open checks")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="sale_order_status_idx")
        ]
        constraints = [_percent_range("sale_order_discount_range")]

    def __str__(self) -> str:
        return self.label or str(self.id)


class OrderLineQuerySet(models.QuerySet):
    def live(self) -> "OrderLineQuerySet":
        """Not removed nor voided."""
        return self.filter(removed_at__isnull=True)

    def unpaid(self) -> "OrderLineQuerySet":
        """Not charged by any sale yet."""
        return self.filter(sale__isnull=True)


class OrderLine(UUIDModel):
    """A working row of an open check: its price, unit and tax category are frozen when it is added."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("open check"),
    )
    position = models.PositiveIntegerField(_("position"))
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("department"),
    )
    name = models.CharField(_("name"), max_length=200)
    sku = models.CharField(_("SKU"), max_length=64, blank=True)
    is_service = models.BooleanField(_("service"), default=False)
    category_id = models.UUIDField(_("product category"), null=True, blank=True)
    # The unit of the quantity and the one the price refers to, frozen with their exact factor.
    unit = models.CharField(_("unit"), max_length=8, default="ud")
    unit_factor_num = models.PositiveBigIntegerField(default=1)
    unit_factor_den = models.PositiveBigIntegerField(default=1)
    increment = models.DecimalField(_("step"), default=Decimal("1"), **QUANTITY)
    price_quantity = models.DecimalField(
        _("price quantity"), default=Decimal("1"), **QUANTITY
    )
    pricing_unit = models.CharField(_("pricing unit"), max_length=8, default="ud")
    pricing_factor_num = models.PositiveBigIntegerField(default=1)
    pricing_factor_den = models.PositiveBigIntegerField(default=1)
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    unit_price = models.PositiveBigIntegerField(_("price"))
    cost = models.PositiveBigIntegerField(_("cost"), default=0)
    tax_category_key = models.CharField(_("tax category"), max_length=80)
    discount_percent = models.DecimalField(
        _("discount (%)"), default=Decimal("0"), **PERCENT
    )
    discount_approved_by = models.CharField(
        _("discount approved by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    is_gift = models.BooleanField(_("comp"), default=False)
    gift_reason = models.CharField(_("comp reason"), max_length=200, blank=True)
    notes = models.CharField(_("note"), max_length=255, blank=True)
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    line_total = models.BigIntegerField(_("line total"), default=0)
    round_no = models.PositiveIntegerField(_("round"), default=0)
    fired_at = models.DateTimeField(_("sent to the kitchen at"), null=True, blank=True)
    sale = models.ForeignKey(
        "Sale",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_lines",
        verbose_name=_("sale"),
    )
    removed_at = models.DateTimeField(_("removed at"), null=True, blank=True)
    void_reason = models.CharField(_("void reason"), max_length=255, blank=True)
    voided_by = models.CharField(
        _("voided by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    objects = OrderLineQuerySet.as_manager()

    class Meta:
        verbose_name = _("open check line")
        verbose_name_plural = _("open check lines")
        ordering = ["position", "id"]
        indexes = [
            models.Index(fields=["order", "position"], name="sale_orderline_order_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sale_orderline_quantity_positive"
            ),
            _percent_range("sale_orderline_discount_range"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.name}"

    @property
    def is_live(self) -> bool:
        return self.removed_at is None

    @property
    def is_fired(self) -> bool:
        return self.fired_at is not None


class Sale(UUIDModel):
    """A charge: the fiscal record. Never edited; corrected by its void or its refunds."""

    class Status(models.TextChoices):
        COMPLETED = "completed", _("Completed")
        VOIDED = "voided", _("Voided")
        REFUNDED = "refunded", _("Refunded")

    number = models.CharField(_("number"), max_length=24, unique=True)
    business_day = models.DateField(_("business day"))
    sequence = models.PositiveIntegerField(_("number of the day"))
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.COMPLETED
    )
    document_type = models.CharField(
        _("document"),
        max_length=8,
        choices=Settings.DocumentType.choices,
        default=Settings.DocumentType.TICKET,
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales",
        verbose_name=_("open check"),
    )
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("customer"),
    )
    customer_name = models.CharField(_("customer name"), max_length=200, blank=True)
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    appointment_id = models.UUIDField(_("appointment"), null=True, blank=True)
    tax_included = models.BooleanField(_("prices include VAT"), default=True)
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    subtotal = models.BigIntegerField(_("taxable base"), default=0)
    tax_total = models.BigIntegerField(_("tax"), default=0)
    discount_percent = models.DecimalField(
        _("discount (%)"), default=Decimal("0"), **PERCENT
    )
    discount_amount = models.BigIntegerField(_("discounts"), default=0)
    gift_total = models.BigIntegerField(_("comps at cost"), default=0)
    total = models.BigIntegerField(_("total"), default=0)
    tendered_total = models.BigIntegerField(_("tendered"), default=0)
    change_total = models.BigIntegerField(_("change"), default=0)
    refunded_total = models.BigIntegerField(_("refunded"), default=0)
    # ``[{rate_pct, label, base, tax}]`` by rate, as the document prints it.
    tax_breakdown = models.JSONField(_("tax breakdown"), default=list, blank=True, encoder=DjangoJSONEncoder)
    payment_method_name = models.CharField(_("payment"), max_length=60, blank=True)
    idempotency_key = models.CharField(_("attempt key"), max_length=128, unique=True)
    notes = models.TextField(_("notes"), blank=True)
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    voided_by = models.CharField(
        _("voided by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    void_reason = models.CharField(_("void reason"), max_length=500, blank=True)
    created_at = models.DateTimeField(_("charged at"), default=timezone.now)
    created_by = models.CharField(
        _("charged by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("sale")
        verbose_name_plural = _("sales")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["business_day", "sequence"], name="sale_sale_day_idx"),
            models.Index(
                fields=["status", "business_day"], name="sale_sale_status_idx"
            ),
            models.Index(fields=["-created_at", "-id"], name="sale_sale_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    subtotal__gte=0,
                    tax_total__gte=0,
                    total__gte=0,
                    gift_total__gte=0,
                    refunded_total__gte=0,
                ),
                name="sale_sale_amounts_not_negative",
            ),
            models.CheckConstraint(
                condition=Q(refunded_total__lte=F("total")),
                name="sale_sale_refund_within_total",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def refundable_total(self) -> int:
        return (
            self.total - self.refunded_total
            if self.status == self.Status.COMPLETED
            else 0
        )


class SaleLine(UUIDModel):
    """The fiscal copy of a charged line."""

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="lines", verbose_name=_("sale")
    )
    position = models.PositiveIntegerField(_("position"))
    order_line_id = models.UUIDField(_("open check line"), null=True, blank=True)
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    department_id = models.UUIDField(_("department"), null=True, blank=True)
    name = models.CharField(_("name"), max_length=200)
    sku = models.CharField(_("SKU"), max_length=64, blank=True)
    is_service = models.BooleanField(_("service"), default=False)
    category_id = models.UUIDField(_("product category"), null=True, blank=True)
    unit = models.CharField(_("unit"), max_length=8, default="ud")
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    unit_price = models.PositiveBigIntegerField(_("price"))
    price_quantity = models.DecimalField(
        _("price quantity"), default=Decimal("1"), **QUANTITY
    )
    pricing_unit = models.CharField(_("pricing unit"), max_length=8, default="ud")
    cost = models.PositiveBigIntegerField(_("cost"), default=0)
    discount_percent = models.DecimalField(
        _("discount (%)"), default=Decimal("0"), **PERCENT
    )
    is_gift = models.BooleanField(_("comp"), default=False)
    gift_reason = models.CharField(_("comp reason"), max_length=200, blank=True)
    notes = models.CharField(_("note"), max_length=255, blank=True)
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    tax_category_key = models.CharField(_("tax category"), max_length=80)
    tax_rate = models.DecimalField(_("rate (%)"), max_digits=6, decimal_places=2)
    tax_country_code = models.CharField(_("tax country"), max_length=2)
    tax_region_code = models.CharField(_("tax region"), max_length=6, blank=True)
    tax_rule_id = models.UUIDField(_("tax rule"), null=True, blank=True)
    net_amount = models.BigIntegerField(_("base"))
    tax_amount = models.BigIntegerField(_("tax"))
    line_total = models.BigIntegerField(_("total"))
    # ``[{rule_id, label, tax_type, rate_pct, tax}]``: the rule's components over this line's base.
    tax_components = models.JSONField(_("tax components"), default=list, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        verbose_name = _("sale line")
        verbose_name_plural = _("sale lines")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sale_saleline_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(line_total=F("net_amount") + F("tax_amount")),
                name="sale_saleline_squares",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.name}"


class SalePayment(UUIDModel):
    """One tender of a sale; change only comes out of cash."""

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="payments", verbose_name=_("sale")
    )
    position = models.PositiveIntegerField(_("position"))
    method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("method"),
    )
    method_name = models.CharField(_("method name"), max_length=60)
    method_type = models.CharField(
        _("method type"), max_length=16, choices=PaymentMethod.Type.choices
    )
    amount = models.PositiveBigIntegerField(_("amount"))
    tendered = models.PositiveBigIntegerField(_("tendered"))
    change = models.PositiveBigIntegerField(_("change"), default=0)
    reference = models.CharField(_("reference"), max_length=128, blank=True)

    class Meta:
        verbose_name = _("sale payment")
        verbose_name_plural = _("sale payments")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="sale_payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(change=F("tendered") - F("amount")),
                name="sale_payment_change",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.method_name} {self.amount}"


class SaleCounter(UUIDModel):
    """The last number given on a business day."""

    day = models.DateField(_("business day"), unique=True)
    last = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("sale counter")
        verbose_name_plural = _("sale counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {self.last}"


class Refund(UUIDModel):
    """Money given back on a sale (by tender), with the lines that return."""

    sale = models.ForeignKey(
        Sale, on_delete=models.PROTECT, related_name="refunds", verbose_name=_("sale")
    )
    total = models.PositiveBigIntegerField(_("total"))
    reason = models.CharField(_("reason"), max_length=500)
    note = models.CharField(_("note"), max_length=500, blank=True)
    idempotency_key = models.CharField(
        _("attempt key"), max_length=128, unique=True, null=True, blank=True
    )
    created_at = models.DateTimeField(_("refunded at"), default=timezone.now)
    created_by = models.CharField(
        _("refunded by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gt=0), name="sale_refund_total_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.sale_id}: {self.total}"


class RefundPayment(UUIDModel):
    refund = models.ForeignKey(
        Refund,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("refund"),
    )
    position = models.PositiveIntegerField(_("position"))
    sale_payment = models.ForeignKey(
        SalePayment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("original payment"),
    )
    method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("method"),
    )
    method_name = models.CharField(_("method name"), max_length=60)
    method_type = models.CharField(
        _("method type"), max_length=16, choices=PaymentMethod.Type.choices
    )
    amount = models.PositiveBigIntegerField(_("amount"))

    class Meta:
        verbose_name = _("refund payment")
        verbose_name_plural = _("refund payments")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="sale_refundpayment_positive"
            )
        ]

    def __str__(self) -> str:
        return f"{self.method_name} {self.amount}"


class RefundLine(UUIDModel):
    refund = models.ForeignKey(
        Refund, on_delete=models.CASCADE, related_name="lines", verbose_name=_("refund")
    )
    sale_line = models.ForeignKey(
        SaleLine,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("line"),
    )
    quantity = models.DecimalField(_("quantity"), **QUANTITY)

    class Meta:
        verbose_name = _("refunded line")
        verbose_name_plural = _("refunded lines")
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="sale_refundline_quantity_positive"
            ),
            models.UniqueConstraint(
                fields=["refund", "sale_line"], name="sale_refundline_once_per_refund"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.sale_line_id}"
