"""Models of the invoice app.

- ``InvoiceSeries`` numbers the documents of one code (``TICKET``, ``FACT``, ``RECT``…) in one year: its
  counter is raised with ``UPDATE … RETURNING`` in the transaction of the document (never a sequence),
  and its prefix and format freeze with its first number.
- ``Issuer`` is the business's tax identity (one row), copied on every document; the SaaS will fill it
  (``invoice.issuer.sync``, WORKBOOK «Para quien lo mantiene»).
- ``Invoice`` is a fiscal document, never edited nor deleted: F1 (full), F2 (simplified, the ticket), F3
  (full that substitutes a ticket) and R1–R5 (rectifying, by differences, with negative amounts). It
  copies its issuer and its recipient; only ``status`` and ``paid_at`` ever change.
- ``InvoiceLine`` is one concept of a document, its money squared (base + tax = total).

Money is in whole cents with a sign (a rectifying document is negative); quantities have three
decimals, as the sale's. Phase 1 has no tenancy (like ``apps.sale``).
"""

from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

QUANTITY = {"max_digits": 15, "decimal_places": 3}
RATE = {"max_digits": 6, "decimal_places": 2}
ACTOR_MAX_LENGTH = 128
SERIES_CODE_RE = r"^[A-Z0-9][A-Z0-9_-]*$"
SERIES_CODE_MAX_LENGTH = 20
FORMAT_MAX_LENGTH = 60
NUMBER_MAX_LENGTH = 60
#: What VeriFactu's record holds (SuministroInformacion.xsd): NombreRazon ≤ 120, IDOtro's ID ≤ 20.
NAME_MAX_LENGTH = 120
TAX_ID_MAX_LENGTH = 20
#: A unit price in cents with two decimals (a price without VAT of a price that had it: 0.8264 €).
UNIT_PRICE = {"max_digits": 20, "decimal_places": 2}


class InvoiceType(models.TextChoices):
    F1 = "F1", _("Invoice (F1)")
    F2 = "F2", _("Simplified invoice (F2)")
    F3 = "F3", _("Invoice replacing a simplified one (F3)")
    R1 = (
        "R1",
        _("Rectifying invoice: error founded in law and art. 80 One, Two and Six (R1)"),
    )
    R2 = "R2", _("Rectifying invoice: art. 80 Three, insolvency (R2)")
    R3 = "R3", _("Rectifying invoice: art. 80 Four, bad debts (R3)")
    R4 = "R4", _("Rectifying invoice: other causes (R4)")
    R5 = "R5", _("Rectifying invoice of a simplified invoice (R5)")


ORDINARY_TYPES = ("F1", "F2", "F3")
RECTIFYING_TYPES = ("R1", "R2", "R3", "R4", "R5")
SIMPLIFIED_TYPES = ("F2", "R5")

#: The factory series (created on first use) → their name in the reader's language. The row keeps the
#: English name; a series the business names keeps its own.
FACTORY_SERIES_NAMES = {
    "TICKET": ("POS tickets", _("POS tickets")),
    "FACT": ("Invoices", _("Invoices")),
    "RECT": ("Rectifying invoices", _("Rectifying invoices")),
}


class InvoiceSeries(UUIDModel):
    code = models.CharField(
        _("code"),
        max_length=SERIES_CODE_MAX_LENGTH,
        validators=[
            RegexValidator(
                SERIES_CODE_RE,
                _(
                    "Use capital letters, digits, hyphens and underscores, starting with a letter or a digit."
                ),
            )
        ],
    )
    name = models.CharField(_("name"), max_length=120, blank=True)
    invoice_type = models.CharField(
        _("invoice type"), max_length=2, choices=InvoiceType.choices
    )
    year = models.PositiveSmallIntegerField(
        _("year"), validators=[MinValueValidator(2000), MaxValueValidator(2999)]
    )
    prefix = models.CharField(_("prefix"), max_length=20, blank=True)
    # Empty = ``{prefix}-{year}-{seq:06d}`` (``fiscal.DEFAULT_FORMAT``).
    format = models.CharField(
        _("number format"), max_length=FORMAT_MAX_LENGTH, blank=True
    )
    # The last number given; the next document takes current_number + 1.
    current_number = models.IntegerField(_("current number"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    is_default = models.BooleanField(_("default series"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("numbering series")
        verbose_name_plural = _("numbering series")
        ordering = ["-year", "code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "year"], name="invoice_series_code_year"
            ),
            models.UniqueConstraint(
                fields=["year"],
                condition=Q(is_default=True),
                name="invoice_series_one_default_a_year",
            ),
            models.CheckConstraint(
                condition=Q(current_number__gte=0),
                name="invoice_series_counter_positive",
            ),
            models.CheckConstraint(
                condition=Q(year__gte=2000, year__lte=2999),
                name="invoice_series_year_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} {self.year}"

    @property
    def display_name(self) -> str:
        """A factory series keeps its English name in the row and reads in the reader's language."""
        factory = FACTORY_SERIES_NAMES.get(self.code)
        if factory and self.name == factory[0]:
            return str(factory[1])
        return self.name


class Issuer(UUIDModel):
    """The business's tax identity: one row at most, copied on every document issued after it."""

    class Source(models.TextChoices):
        MANUAL = "manual", _("Typed in the Hub")
        SAAS = "saas", _("From the ERPlora account")

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    legal_name = models.CharField(_("legal name"), max_length=NAME_MAX_LENGTH)
    tax_id = models.CharField(_("tax ID"), max_length=TAX_ID_MAX_LENGTH)
    address = models.CharField(_("address"), max_length=255)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    province = models.CharField(_("province"), max_length=100, blank=True)
    # ISO 3166-1 alpha-2.
    country = models.CharField(_("country"), max_length=2, default="ES")
    source = models.CharField(
        _("source"), max_length=8, choices=Source.choices, default=Source.MANUAL
    )
    # The version of the SaaS's photo it came with: an older photo is ignored.
    synced_version = models.BigIntegerField(_("synced version"), null=True, blank=True)
    synced_at = models.DateTimeField(_("synced at"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("issuer")
        verbose_name_plural = _("issuer")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="invoice_issuer_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="invoice_issuer_singleton"
            ),
        ]

    def __str__(self) -> str:
        return self.legal_name

    @property
    def configured(self) -> bool:
        """What a document cannot go without: name, tax ID and address."""
        return all(
            part.strip() for part in (self.legal_name, self.tax_id, self.address)
        )

    @property
    def address_line(self) -> str:
        """``Street, 28001 Madrid (Madrid)``: what a document prints as the issuer's address."""
        town = " ".join(
            part for part in (self.postal_code.strip(), self.city.strip()) if part
        )
        line = ", ".join(part for part in (self.address.strip(), town) if part)
        province = self.province.strip()
        return f"{line} ({province})" if province else line


class Invoice(UUIDModel):
    class Status(models.TextChoices):
        # With their own context: Sales and Customers translate the same words for other things («Emitido»,
        # «Cobrada»), and the app listed first in INSTALLED_APPS would win.
        ISSUED = "issued", pgettext_lazy("invoice status", "Issued")
        PAID = "paid", pgettext_lazy("invoice status", "Paid")
        CANCELLED = "cancelled", pgettext_lazy("invoice status", "Cancelled")

    class Source(models.TextChoices):
        SALE = "sale", _("POS sale")
        MANUAL = "manual", _("Manual")
        SUBSTITUTION = "substitution", _("Replaces a simplified invoice")
        RECTIFICATION = "rectification", _("Rectification")
        REFUND = "refund", _("Sale refund")
        VOID = "void", _("Sale void")

    class RectificationKind(models.TextChoices):
        DIFFERENCES = "I", _("By differences")
        SUBSTITUTION = "S", _("By substitution")

    invoice_type = models.CharField(
        _("invoice type"), max_length=2, choices=InvoiceType.choices
    )
    series = models.ForeignKey(
        InvoiceSeries,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("series"),
    )
    series_code = models.CharField(_("series code"), max_length=SERIES_CODE_MAX_LENGTH)
    year = models.PositiveSmallIntegerField(_("year"))
    sequence = models.PositiveIntegerField(_("sequence"))
    # VeriFactu's NumSerieFactura: at most 60 printable ASCII characters (checked when a series is made).
    number = models.CharField(_("number"), max_length=NUMBER_MAX_LENGTH)
    issue_date = models.DateField(_("issue date"))
    operation_date = models.DateField(_("operation date"))
    issued_at = models.DateTimeField(_("issued at"), default=timezone.now)
    # The issuer as it was when the document was issued.
    # VeriFactu's NombreRazon (≤ 120) and NIF / IDOtro ID (≤ 20): SuministroInformacion.xsd.
    issuer_name = models.CharField(_("issuer name"), max_length=NAME_MAX_LENGTH)
    issuer_tax_id = models.CharField(_("issuer tax ID"), max_length=TAX_ID_MAX_LENGTH)
    issuer_address = models.CharField(_("issuer address"), max_length=400, blank=True)
    issuer_country = models.CharField(_("issuer country"), max_length=2, blank=True)
    # The recipient: a copy (editing the card never changes an issued document); the card, a link.
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("customer"),
    )
    customer_name = models.CharField(
        _("customer name"), max_length=NAME_MAX_LENGTH, blank=True
    )
    customer_tax_id = models.CharField(
        _("customer tax ID"), max_length=TAX_ID_MAX_LENGTH, blank=True
    )
    customer_address = models.CharField(
        _("customer address"), max_length=500, blank=True
    )
    # ISO 3166-1 alpha-2; empty = the business's own country.
    customer_country = models.CharField(_("customer country"), max_length=2, blank=True)
    # The AEAT's IDType of a foreign document (02 EU VAT number … 07 not registered); empty = a NIF.
    customer_id_type = models.CharField(
        _("customer document type"), max_length=2, blank=True
    )
    # The reason of a rectifying document (DescripcionOperacion); empty otherwise.
    description = models.CharField(_("description"), max_length=500, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    base_amount = models.BigIntegerField(_("taxable base"))
    tax_amount = models.BigIntegerField(_("tax"))
    total_amount = models.BigIntegerField(_("total"))
    # One entry per fiscal key (WORKBOOK «Para quien lo mantiene»).
    tax_breakdown = models.JSONField(
        _("tax breakdown"), default=list, blank=True, encoder=DjangoJSONEncoder
    )
    currency = models.CharField(_("currency"), max_length=3, default="EUR")
    source_type = models.CharField(
        _("source"), max_length=16, choices=Source.choices, default=Source.MANUAL
    )
    source_sale = models.ForeignKey(
        "sale.Sale",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("sale"),
    )
    source_refund = models.ForeignKey(
        "sale.Refund",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("refund"),
    )
    rectifies = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rectifications",
        verbose_name=_("rectifies"),
    )
    substitutes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="substitutions",
        verbose_name=_("replaces"),
    )
    rectification_kind = models.CharField(
        _("rectification kind"),
        max_length=1,
        choices=RectificationKind.choices,
        blank=True,
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.ISSUED
    )
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    # ERPlora's own invoices (its platform hub, PLAN-SAAS §4): the SaaS's id of the invoice, which makes posting it
    # again harmless, and the language its document is printed in (its payer's). Empty for the business's own.
    platform_ref = models.UUIDField(_("ERPlora invoice"), null=True, blank=True, unique=True)
    language = models.CharField(_("document language"), max_length=8, blank=True)
    created_by = models.CharField(
        _("issued by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-issued_at", "-id"]
        indexes = [
            models.Index(fields=["-issued_at", "-id"], name="invoice_recent_idx"),
            models.Index(fields=["issue_date", "id"], name="invoice_issue_date_idx"),
            models.Index(fields=["status", "issue_date"], name="invoice_status_idx"),
            models.Index(
                fields=["series_code", "year", "sequence"], name="invoice_book_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["series_code", "number"], name="invoice_number_in_series"
            ),
            models.UniqueConstraint(
                fields=["series", "sequence"], name="invoice_sequence_in_series"
            ),
            models.UniqueConstraint(
                fields=["source_sale"],
                condition=Q(source_type="sale"),
                name="invoice_one_per_sale",
            ),
            models.UniqueConstraint(
                fields=["source_sale"],
                condition=Q(source_type="void"),
                name="invoice_one_per_void",
            ),
            models.UniqueConstraint(
                fields=["source_refund"],
                condition=Q(source_refund__isnull=False),
                name="invoice_one_per_refund",
            ),
            models.UniqueConstraint(
                fields=["substitutes"],
                condition=Q(substitutes__isnull=False),
                name="invoice_one_substitute",
            ),
            models.CheckConstraint(
                condition=Q(total_amount=F("base_amount") + F("tax_amount")),
                name="invoice_squares",
            ),
            models.CheckConstraint(
                condition=Q(invoice_type__in=RECTIFYING_TYPES) | Q(total_amount__gte=0),
                name="invoice_ordinary_not_negative",
            ),
            models.CheckConstraint(
                condition=~Q(invoice_type__in=RECTIFYING_TYPES)
                | (Q(total_amount__lte=0) & Q(rectifies__isnull=False)),
                name="invoice_rectifying_negative_and_linked",
            ),
            models.CheckConstraint(
                condition=~Q(invoice_type="F3") | Q(substitutes__isnull=False),
                name="invoice_substitute_linked",
            ),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def is_rectification(self) -> bool:
        return self.invoice_type in RECTIFYING_TYPES

    @property
    def is_simplified(self) -> bool:
        """A ticket (F2) or the rectification of one (R5): it identifies no customer."""
        return self.invoice_type in SIMPLIFIED_TYPES


class InvoiceLine(UUIDModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("invoice"),
    )
    position = models.PositiveIntegerField(_("position"))
    description = models.CharField(_("description"), max_length=255)
    # Signed: a rectifying line carries its sign in the quantity, never in the price.
    quantity = models.DecimalField(_("quantity"), **QUANTITY)
    # RD 1619/2012 art. 6.1.f: the unit price WITHOUT the tax and before any discount, in cents with two
    # decimals; the discount apart, without the tax, with the line's sign. quantity × unit_price −
    # discount_amount is the base (to the cent; the base is the figure that counts).
    unit_price = models.DecimalField(_("unit price"), **UNIT_PRICE)
    discount_amount = models.BigIntegerField(_("discount"), default=0)
    # The main rate and the equivalence surcharge apart (21 + 5.2, never a combined 26.2).
    tax_rate = models.DecimalField(_("rate (%)"), **RATE)
    surcharge_rate = models.DecimalField(_("surcharge (%)"), default=0, **RATE)
    tax_category_key = models.CharField(_("tax category"), max_length=80, blank=True)
    base_amount = models.BigIntegerField(_("base"))
    tax_amount = models.BigIntegerField(_("tax"))
    total_amount = models.BigIntegerField(_("total"))
    product_id = models.UUIDField(_("product"), null=True, blank=True)
    sale_line_id = models.UUIDField(_("sale line"), null=True, blank=True)

    class Meta:
        verbose_name = _("invoice line")
        verbose_name_plural = _("invoice lines")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(total_amount=F("base_amount") + F("tax_amount")),
                name="invoice_line_squares",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="invoice_line_price_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.description}"
