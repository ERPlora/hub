"""The departments of the open price and the quick notes of a line."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.sale.models.fields import _actor


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
    created_by = _actor(_("created by"))

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
    created_by = _actor(_("created by"))

    class Meta:
        verbose_name = _("quick note")
        verbose_name_plural = _("quick notes")
        ordering = ["sort_order", "text", "id"]

    def __str__(self) -> str:
        return self.text
