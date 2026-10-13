"""Models of the demo app: an item with a status and a note, and its lines.

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live
notifications are per scope. Phase 2 moves them to each hub's database.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class Item(UUIDModel):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        DONE = "done", _("Done")

    name = models.CharField(_("name"), max_length=120)
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.OPEN)
    note = models.TextField(_("note"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("item")
        verbose_name_plural = _("items")
        # The order of demo.item.list: most recently changed first, id as the tie-break.
        ordering = ["-updated_at", "id"]
        indexes = [models.Index(fields=["-updated_at", "id"], name="demo_item_updated_idx")]

    def __str__(self) -> str:
        return self.name


class ItemLine(UUIDModel):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="lines", verbose_name=_("item"))
    text = models.CharField(_("text"), max_length=200)
    qty = models.DecimalField(_("quantity"), max_digits=10, decimal_places=3)
    position = models.PositiveIntegerField(_("position"))
    # Set by the client so that repeating demo.item.add_line does not add the line twice.
    client_line_id = models.UUIDField(_("client line id"), null=True, blank=True)

    class Meta:
        verbose_name = _("line")
        verbose_name_plural = _("lines")
        ordering = ["position", "id"]
        constraints = [
            # NULLs are distinct in Postgres: lines without a client id never collide.
            models.UniqueConstraint(fields=["item", "client_line_id"], name="demo_line_client_id_unique"),
        ]

    def __str__(self) -> str:
        return self.text
