"""The till settings of the business."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models.fields import _actor


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
    updated_by = _actor(_("updated by"))

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
