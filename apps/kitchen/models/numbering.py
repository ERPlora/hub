"""The ticket counter of each business day."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class DayCounter(UUIDModel):
    """The last ticket number of a business day (``YYYYMMDD-NNNN``), taken with ``select_for_update``."""

    day = models.DateField(_("day"), unique=True)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("day counter")
        verbose_name_plural = _("day counters")

    def __str__(self) -> str:
        return f"{self.day}: {self.last_number}"
