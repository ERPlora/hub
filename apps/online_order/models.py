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
