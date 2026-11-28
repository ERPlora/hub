"""The tenders of a sale: the money each payment method took."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models.payment_methods import PaymentMethod
from apps.sale.models.sales import Sale


class Tender(UUIDModel):
    """Money that moved by one payment method, named as it was then: a leg of a charge or of a refund."""

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

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.method_name} {self.amount}"


class SalePayment(Tender):
    """One tender of a sale; change only comes out of cash."""

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="payments", verbose_name=_("sale")
    )
    tendered = models.PositiveBigIntegerField(_("tendered"))
    change = models.PositiveBigIntegerField(_("change"), default=0)
    reference = models.CharField(_("reference"), max_length=128, blank=True)
    # What another app adds on top of the sale (a tip): charged with the tender, never part of the sale's total or tax.
    extra = models.PositiveBigIntegerField(_("added amount"), default=0, db_default=0)
    extra_label = models.CharField(_("added amount label"), max_length=60, blank=True, default="", db_default="")

    class Meta:
        verbose_name = _("sale payment")
        verbose_name_plural = _("sale payments")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="sale_payment_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(change=F("tendered") - F("amount") - F("extra")),
                name="sale_payment_change",
            ),
        ]
