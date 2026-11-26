from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class TableCode(UUIDModel):
    """The code a table's QR carries: it opens that table's page until the table's code is regenerated."""

    # A table of Tables, by its id (no foreign key across apps, as Tables keeps Sales' order).
    table_id = models.UUIDField(_("table"), unique=True)
    # Kept as drawn, because the sheet is printed again.
    code = models.CharField(_("code"), max_length=32, unique=True)
    issued_at = models.DateTimeField(_("generated at"), default=timezone.now)

    class Meta:
        verbose_name = _("table code")
        verbose_name_plural = _("table codes")
        ordering = ["issued_at", "id"]

    def __str__(self) -> str:
        return self.code


class Order(UUIDModel):
    """What a table's customer sends from their phone: it waits as pending until an employee decides on it."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    # The table whose QR it was sent from, by its id in Tables.
    table_id = models.UUIDField(_("table"))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.PENDING)
    # In the currency's minor unit, as the server priced it.
    total = models.PositiveIntegerField(_("total"))
    created_at = models.DateTimeField(_("sent at"), default=timezone.now)

    class Meta:
        verbose_name = _("online order")
        verbose_name_plural = _("online orders")
        ordering = ["created_at", "id"]


class OrderLine(UUIDModel):
    """A dish with its options, or a set menu with its dishes, priced when it was sent."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines", verbose_name=_("online order"))
    position = models.PositiveSmallIntegerField(_("position"))
    # A product of Inventory or a menu of Menus and combos, by its id: exactly one of them.
    product_id = models.UUIDField(_("dish"), null=True, blank=True)
    combo_id = models.UUIDField(_("set menu"), null=True, blank=True)
    name = models.CharField(_("name"), max_length=200)
    quantity = models.PositiveSmallIntegerField(_("quantity"))
    unit_price = models.PositiveIntegerField(_("unit price"))
    notes = models.CharField(_("notes"), max_length=200, blank=True)
    # The dish's options or the set menu's dishes, each with its id, name and supplement as priced.
    picks = models.JSONField(_("choices"), default=list, blank=True)

    class Meta:
        verbose_name = _("online order line")
        verbose_name_plural = _("online order lines")
        ordering = ["order", "position"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(product_id__isnull=False, combo_id__isnull=True)
                | models.Q(product_id__isnull=True, combo_id__isnull=False),
                name="online_order_line_dish_or_set_menu",
            ),
        ]
