"""The appointments' numbers: one counter per business day."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class Counter(UUIDModel):
    """The last number handed out on a business day (``APT-YYYYMMDD-NNNN``); never a sequence."""

    day = models.DateField(_("day"), unique=True)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("appointment counter")
        verbose_name_plural = _("appointment counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day:%Y%m%d}: {self.last_number}"
