"""The payment methods the till charges with, and the names of the factory ones."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models.fields import _actor


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
    created_by = _actor(_("created by"))

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
