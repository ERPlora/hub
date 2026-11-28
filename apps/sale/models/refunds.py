"""The refunds of a sale: the money given back by tender and the lines that return with it."""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models.fields import QUANTITY, _actor
from apps.sale.models.payments import SalePayment, Tender
from apps.sale.models.sales import Sale, SaleLine, _fiscal_status


class Refund(UUIDModel):
    """Money given back on a sale (by tender), with the lines that return; no money when only the
    session of a voucher comes back (SALE-F32)."""

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
    created_by = _actor(_("refunded by"))
    # Its rectifying invoice (R1, R5), as Invoicing answered in the same transaction.
    invoice_number = models.CharField(_("rectifying invoice"), max_length=60, blank=True)
    invoice_type = models.CharField(_("rectifying invoice type"), max_length=2, blank=True)
    invoice_status = _fiscal_status(_("rectifying invoice"))

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at", "-id"]
        # Cash register reads the refunds of a shift by their time (CASH_REGISTER-F11, F17).
        indexes = [models.Index(fields=["created_at"], name="sale_refund_created_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(total__gte=0), name="sale_refund_total_not_negative"
            )
        ]

    def __str__(self) -> str:
        return f"{self.sale_id}: {self.total}"


class RefundPayment(Tender):
    refund = models.ForeignKey(
        Refund,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("refund"),
    )
    sale_payment = models.ForeignKey(
        SalePayment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("original payment"),
    )

    class Meta:
        verbose_name = _("refund payment")
        verbose_name_plural = _("refund payments")
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="sale_refundpayment_positive"
            )
        ]


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
