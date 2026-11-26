"""The sales, the fiscal records a charge creates, with their lines and what Invoicing answered for them."""

from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.sale.models.fields import PERCENT, QUANTITY, _actor, _json_list
from apps.sale.models.orders import Order
from apps.sale.models.settings import Settings


class ForeignIdType(models.TextChoices):
    """The AEAT's kinds of document of a foreign customer (``IDType``; a Spanish NIF has none), by the words the
    recipient form of Invoicing gives them, an app Sales does not require (``apps.customer.tax_ids.ID_TYPES``)."""

    EU_VAT = "02", _("EU VAT number")
    PASSPORT = "03", _("Passport")
    FOREIGN_TAX_ID = "04", _("Tax ID of their country")
    RESIDENCE_CERTIFICATE = "05", _("Residence certificate")
    OTHER = "06", _("Other document")
    NOT_REGISTERED = "07", _("Not registered")


class FiscalStatus(models.TextChoices):
    """What Invoicing answered when the sale, its void or a refund asked for its fiscal document, in the
    same transaction (no Invoicing app → «unavailable»; a refusal → «pending», issued later by
    Invoicing's own reaction; nothing to declare, a refund of no money → «none»)."""

    ISSUED = "issued", _("Issued")
    PENDING = "pending", _("Pending")
    UNAVAILABLE = "unavailable", _("Without Invoicing")
    NONE = "none", _("Nothing to declare")


def _fiscal_status(verbose: str):
    return models.CharField(verbose, max_length=12, choices=FiscalStatus.choices, blank=True)


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
    # The recipient of an invoice as it was checked at the till (a ticket keeps them empty): what a
    # document issued later — retrying the charge, «Issue now» — declares, the same as the charge would.
    # ``db_default``: a process still on the previous code inserts sales without them (expand/contract).
    customer_tax_id = models.CharField(
        _("customer tax ID"), max_length=32, blank=True, default="", db_default=""
    )
    customer_address = models.CharField(
        _("customer address"), max_length=500, blank=True, default="", db_default=""
    )
    customer_country = models.CharField(
        _("customer country"), max_length=2, blank=True, default="", db_default=""
    )
    customer_id_type = models.CharField(
        _("customer document type"),
        max_length=2,
        blank=True,
        default="",
        db_default="",
        choices=ForeignIdType.choices,
    )
    staff_id = models.UUIDField(_("served by"), null=True, blank=True)
    appointment_id = models.UUIDField(_("appointment"), null=True, blank=True)
    tax_included = models.BooleanField(_("prices include VAT"), default=True)
    # The business's currency when it was charged (its country's): never rewritten afterwards.
    currency = models.CharField(_("currency"), max_length=3)
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
    # ``[{rate_pct, label, tax_type, regime, qualification, exempt_reason, base, tax}]``: one row per
    # fiscal key and component, as the document prints it and Invoicing declares it.
    tax_breakdown = models.JSONField(
        _("tax breakdown"), default=list, blank=True, encoder=DjangoJSONEncoder
    )
    payment_method_name = models.CharField(_("payment"), max_length=60, blank=True)
    idempotency_key = models.CharField(_("attempt key"), max_length=128, unique=True)
    notes = models.TextField(_("notes"), blank=True)
    # Own context: a sale is «anulada el» as it is «anulada por», not Clientes' «anulado el».
    voided_at = models.DateTimeField(
        pgettext_lazy("sale", "voided at"), null=True, blank=True
    )
    voided_by = _actor(_("voided by"))
    void_reason = models.CharField(_("void reason"), max_length=500, blank=True)
    # The fiscal document Invoicing issued for it (F2 ticket, F1 invoice) and for its void (R5, R1):
    # ids of Invoicing without a foreign key (Invoicing is no requirement of Sales).
    invoice_id = models.UUIDField(_("fiscal document"), null=True, blank=True)
    invoice_number = models.CharField(_("fiscal document number"), max_length=60, blank=True)
    invoice_type = models.CharField(_("fiscal document type"), max_length=2, blank=True)
    invoice_status = _fiscal_status(_("fiscal document"))
    void_invoice_number = models.CharField(
        _("rectifying invoice of the void"), max_length=60, blank=True
    )
    void_invoice_status = _fiscal_status(_("rectifying invoice of the void"))
    created_at = models.DateTimeField(_("charged at"), default=timezone.now)
    created_by = _actor(_("charged by"))

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
            # Cash register reads the voids of a shift by their time (CASH_REGISTER-F11, F17).
            models.Index(
                fields=["voided_at"],
                name="sale_sale_voided_idx",
                condition=Q(voided_at__isnull=False),
            ),
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
    service_id = models.UUIDField(_("service id"), null=True, blank=True)
    voucher_session_id = models.UUIDField(_("voucher session"), null=True, blank=True)
    voucher_grant_id = models.UUIDField(_("voucher"), null=True, blank=True)
    voucher_name = models.CharField(_("voucher name"), max_length=200, blank=True)
    # What the voucher's session is worth to who does the line (SALE-F28), fixed at the charge as Services said it: no
    # money of this sale (the voucher was paid when it was sold), so it is in no total and in no document.
    voucher_value = models.PositiveBigIntegerField(
        _("voucher session value"), default=0, db_default=0
    )
    # What of this line paid for vouchers sold on it, as Services says when it grants them (SERVICE-F14): the money is
    # still the sale's, but it is no production of who sold it: it counts as each session is done (SALE-F28).
    voucher_sold_amount = models.PositiveBigIntegerField(
        _("paid for vouchers"), default=0, db_default=0
    )
    # SALE-F11: the names of the options charged inside the line (the receipt prints them under it), and, on
    # the child line of an option of another tax category, the line of the dish it hangs from.
    modifiers = _json_list(pgettext_lazy("sale", "options"))
    parent_line_id = models.UUIDField(
        _("line it hangs from"), null=True, blank=True
    )
    # SALE-F12: the menu a line charges (or, split per dish, a part of), its name for the receipt's header
    # and its dishes ``[{product_id, product_name, quantity (per menu), is_service, category_id}]``.
    combo_id = models.UUIDField(_("menu"), null=True, blank=True)
    combo_name = models.CharField(
        _("menu name"), max_length=200, blank=True, default="", db_default=""
    )
    components = _json_list(_("dishes"))
    tax_category_key = models.CharField(_("tax category"), max_length=80)
    tax_rate = models.DecimalField(_("rate (%)"), max_digits=6, decimal_places=2)
    tax_country_code = models.CharField(_("tax country"), max_length=2)
    tax_region_code = models.CharField(_("tax region"), max_length=6, blank=True)
    tax_rule_id = models.UUIDField(_("tax rule"), null=True, blank=True)
    net_amount = models.BigIntegerField(_("base"))
    tax_amount = models.BigIntegerField(_("tax"))
    line_total = models.BigIntegerField(_("total"))
    # ``[{rule_id, label, tax_type, rate_pct, tax}]``: the rule's components over this line's base.
    tax_components = models.JSONField(
        _("tax components"), default=list, blank=True, encoder=DjangoJSONEncoder
    )

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

    @property
    def paid_by_voucher(self) -> bool:
        return self.voucher_session_id is not None
