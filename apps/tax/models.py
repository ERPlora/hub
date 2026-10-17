"""Models of the tax app: tax categories, the rules that give them a rate, and the aliases of the importer.

- ``TaxCategory`` is what products and services point to (inventory has a foreign key to it): its
  ``key`` (``restaurant.food``) is the linkable identity and never changes; its name is a label.
- ``TaxRule`` gives a category its rate in a country (or one of its regions) between two dates, with
  its fiscal qualification. A root rule (no ``parent``) may carry components over the same base, such
  as the equivalence surcharge. A rule is never edited or deleted: it gets an end date or is
  deactivated, and a new one is created.
- ``TaxAlias`` is an outside text (``beer``) that the importer of inventory reads as a category.
- ``TaxSettings`` is the business's tax region (``ES-CN``), one row at most: what every calculation that names
  no country reads, with the business's country (TAX-F11).

Phase 1 has no tenancy (like ``apps.demo``): phase 2 moves these tables to each hub's database.
"""

from datetime import date
from typing import NamedTuple

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

#: The shape of a category key: lowercase, starting with a letter; letters, digits, dots and underscores.
CATEGORY_KEY_RE = r"^[a-z][a-z0-9_.]*$"
CATEGORY_KEY_MAX_LENGTH = 80


class Label(NamedTuple):
    name: str
    description: str


#: The name of each factory category in the reader's language (English is the source). The row keeps
#: its English name; a category the business creates has no entry and keeps the text that was typed.
SYSTEM_CATEGORY_LABELS: dict[str, Label] = {
    "restaurant.food": Label(_("Restaurant — food"), ""),
    "restaurant.drink": Label(_("Restaurant — drink"), ""),
    # Served to drink on the premises: a hospitality service at 10 %. To take away: retail.alcohol.
    "restaurant.alcohol": Label(
        _("Restaurant — alcohol"),
        _("Alcoholic drinks served to drink on the premises — art. 91.Uno.2.2 (ES)"),
    ),
    "retail.alcohol": Label(
        _("Retail — alcohol to take away"),
        _("Alcoholic drinks sold to take away or delivered — art. 90 (ES)"),
    ),
    "restaurant.delivery": Label(_("Restaurant — delivery"), ""),
    "service.generic": Label(_("Service — generic"), ""),
    "service.health": Label(
        _("Service — healthcare (VAT exempt)"),
        _(
            "Assistance provided by medical or health professionals — art. 20.Uno.3 (ES)"
        ),
    ),
    "service.education": Label(
        _("Service — education (VAT exempt)"),
        _("Regulated teaching and training — art. 20.Uno.9 (ES)"),
    ),
    "product.generic": Label(_("Product — generic"), ""),
    "product.reduced": Label(_("Product — reduced (food staples, pharmacy)"), ""),
    "product.super_reduced": Label(
        _("Product — super-reduced (bread, books, basics)"), ""
    ),
}


class TaxCategory(UUIDModel):
    key = models.CharField(
        _("key"),
        max_length=CATEGORY_KEY_MAX_LENGTH,
        unique=True,
        validators=[
            RegexValidator(
                CATEGORY_KEY_RE,
                _(
                    "Use lowercase letters, digits, dots and underscores, starting with a letter."
                ),
            )
        ],
    )
    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)
    # A factory category (migration 0002); the ones the business creates are its own.
    is_system = models.BooleanField(_("system"), default=False)
    # As in the current product: the lists show the active ones; no operation archives one yet.
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("tax category")
        verbose_name_plural = _("tax categories")
        ordering = ["key", "id"]

    def __str__(self) -> str:
        return self.key

    @property
    def _label(self) -> Label | None:
        return SYSTEM_CATEGORY_LABELS.get(self.key) if self.is_system else None

    @property
    def display_name(self) -> str:
        """The name to show: a factory category's in the active language, an own one as typed."""
        label = self._label
        return str(label.name) if label else self.name

    @property
    def display_description(self) -> str:
        label = self._label
        return (
            str(label.description) if label and label.description else self.description
        )


class TaxRule(UUIDModel):
    class TaxType(models.TextChoices):
        VAT = "vat", _("VAT")
        IGIC = "igic", _("IGIC (Canary Islands)")
        IPSI = "ipsi", _("IPSI (Ceuta and Melilla)")
        SURCHARGE = "surcharge", _("Surcharge")
        SALES_TAX = "sales_tax", _("Sales tax")
        WITHHOLDING = "withholding", _("Withholding")
        EXCISE = "excise", _("Excise duty")
        IMPORT_DUTY = "import_duty", _("Import duty")

    class OperationClass(models.TextChoices):
        """How the operation is declared; every class but ``subject`` charges no tax."""

        SUBJECT = "subject", _("Subject")
        SUBJECT_REVERSE = "subject_reverse", _("Reverse charge")
        EXEMPT = "exempt", _("Exempt")
        NOT_SUBJECT = "not_subject", _("Not subject")
        NOT_SUBJECT_LOCATION = (
            "not_subject_location",
            _("Not subject (place of supply rules)"),
        )

    # ISO 3166-1 alpha-2 and ISO 3166-2 (``ES-CN``); an empty region is the whole country.
    country_code = models.CharField(_("country"), max_length=2)
    region_code = models.CharField(_("region"), max_length=6, blank=True)
    category = models.ForeignKey(
        TaxCategory,
        on_delete=models.PROTECT,
        related_name="rules",
        verbose_name=_("tax category"),
    )
    rate_pct = models.DecimalField(_("rate (%)"), max_digits=5, decimal_places=2)
    tax_type = models.CharField(
        _("tax type"), max_length=16, choices=TaxType.choices, default=TaxType.VAT
    )
    operation_class = models.CharField(
        _("qualification"),
        max_length=24,
        choices=OperationClass.choices,
        default=OperationClass.SUBJECT,
    )
    # Codes of the jurisdiction (AEAT's OperacionExenta and ClaveRegimen), kept opaque; an empty regime
    # is the general one (01). The cause is kept on an exempt rule only.
    exempt_reason = models.CharField(_("exemption cause"), max_length=10, blank=True)
    regime_key = models.CharField(_("regime"), max_length=10, blank=True)
    # A component (the equivalence surcharge) hangs from a root rule of the same country, region and
    # category; there is a single level.
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="components",
        verbose_name=_("root rule"),
    )
    component_label = models.CharField(_("component label"), max_length=120, blank=True)
    # Inclusive; empty = since always / for ever.
    valid_from = models.DateField(_("valid from"), null=True, blank=True)
    valid_to = models.DateField(_("valid to"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("tax rule")
        verbose_name_plural = _("tax rules")
        ordering = ["country_code", "region_code", "category", "id"]
        indexes = [
            models.Index(
                fields=["country_code", "category", "region_code"],
                name="tax_rule_lookup_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(rate_pct__gte=0, rate_pct__lte=100),
                name="tax_rule_rate_range",
            ),
            # Reverse charge, exempt and not subject reach the tax agency without a quota.
            models.CheckConstraint(
                condition=Q(operation_class="subject") | Q(rate_pct=0),
                name="tax_rule_no_rate_without_tax",
            ),
            models.CheckConstraint(
                condition=Q(valid_from__isnull=True)
                | Q(valid_to__isnull=True)
                | Q(valid_from__lte=F("valid_to")),
                name="tax_rule_valid_range",
            ),
            # The natural key of a root (the current product's ix_tax_rule_root_natural): one root per
            # country, region, category and first day, deactivated ones included. An empty first day
            # is «since always», so two of them are the same key; components share their root's slot.
            models.UniqueConstraint(
                fields=["country_code", "category", "region_code", "valid_from"],
                condition=Q(parent__isnull=True),
                nulls_distinct=False,
                name="tax_rule_root_natural_key",
            ),
        ]

    def __str__(self) -> str:
        region = f" {self.region_code}" if self.region_code else ""
        return f"{self.country_code}{region} · {self.category.key} · {self.rate_pct} %"

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def label(self) -> str:
        """How a component is named in a breakdown: its label, or else its tax type."""
        return self.component_label or self.tax_type

    def in_force_on(self, day: date) -> bool:
        """Whether ``day`` is within the validity range (inclusive; an empty end is open)."""
        return (self.valid_from is None or self.valid_from <= day) and (
            self.valid_to is None or day <= self.valid_to
        )


class TaxAlias(UUIDModel):
    class Source(models.TextChoices):
        SHIPPED = "shipped", _("Shipped")
        LEARNED = "learned", _("Learned")

    # Normalised: lowercase, single spaces, no spaces at the ends (schemas.normalize_text).
    alias = models.CharField(_("alias"), max_length=200, unique=True)
    category = models.ForeignKey(
        TaxCategory,
        on_delete=models.PROTECT,
        related_name="aliases",
        verbose_name=_("tax category"),
    )
    source = models.CharField(
        _("source"), max_length=8, choices=Source.choices, default=Source.LEARNED
    )
    # As in the current product: the lists and the importer read the active ones.
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("tax category alias")
        verbose_name_plural = _("tax category aliases")
        ordering = ["alias", "id"]

    def __str__(self) -> str:
        return self.alias


#: Who changed a row: the operation's actor, cut as the outbox keeps it.
ACTOR_MAX_LENGTH = 128
#: How a business without a region reads in the admin.
WHOLE_COUNTRY = _("Whole country")


class TaxSettings(UUIDModel):
    """The business's tax region: empty is the whole country (Spain's VAT); ``ES-CN`` charges IGIC and
    ``ES-CE``/``ES-ML`` IPSI, by the rules of that region (TAX-F11). One row at most."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    # ISO 3166-2 (``ES-CN``), of the business's country.
    region_code = models.CharField(_("region"), max_length=6, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(_("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True)

    class Meta:
        verbose_name = _("tax settings")
        verbose_name_plural = _("tax settings")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="tax_settings_single_row"),
            models.CheckConstraint(condition=Q(singleton=True), name="tax_settings_singleton"),
        ]

    def __str__(self) -> str:
        return self.region_code or str(WHOLE_COUNTRY)
