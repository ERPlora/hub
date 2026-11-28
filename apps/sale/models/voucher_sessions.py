"""The voucher sessions done outside the till, which count in the production of who did them."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class VoucherSession(UUIDModel):
    """A voucher's session a professional did outside the till (SERVICE-F21), as Services delivered it: no line of a
    sale carries it, so what it is worth counts in her production from here (SALE-F28), on the business day it was
    spent. Like a line's ``voucher_value``, it is no money of the period (the voucher was paid when it was sold) and
    it is fixed when Services tells it: nothing edits it. A session of the till is never here: its line says it."""

    # Opaque ids of Services' session and of Staff's professional (not requirements of Sales).
    session_id = models.UUIDField(_("voucher session"), unique=True)
    staff_id = models.UUIDField(_("done by"))
    business_day = models.DateField(_("business day"))
    value = models.PositiveBigIntegerField(_("voucher session value"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("voucher session done outside the till")
        verbose_name_plural = _("voucher sessions done outside the till")
        ordering = ["-business_day", "-id"]
        indexes = [
            models.Index(fields=["business_day", "staff_id"], name="sale_vouchersession_day_idx")
        ]

    def __str__(self) -> str:
        return f"{self.staff_id}: {self.value}"
