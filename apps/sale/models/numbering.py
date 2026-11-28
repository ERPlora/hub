"""The numbers of the sales: one counter per business day."""

import datetime as dt

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

NUMBER_WIDTH = 4


def sale_number(day: dt.date, sequence: int) -> str:
    """``AAAAMMDD-NNNN``: four digits as a minimum width, never a ceiling (the 10.000th is ``-10000``)."""
    return f"{day:%Y%m%d}-{sequence:0{NUMBER_WIDTH}d}"


class SaleCounter(UUIDModel):
    """The last number given on a business day."""

    day = models.DateField(_("business day"), unique=True)
    last = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("sale counter")
        verbose_name_plural = _("sale counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}: {self.last}"
