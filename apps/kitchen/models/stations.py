"""The places where dishes are made: their screen filter and their printer."""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from apps.kitchen.models.fields import Audited, Destination, PrinterUsage, _destination, _in, _printer_usage

#: A station's colour: ``#RRGGBB``.
COLOR_RE = r"^#[0-9A-Fa-f]{6}$"


class Station(Audited):
    """A place where dishes are made (grill, bar, desserts): its screen filter and its printer."""

    name = models.CharField(_("name"), max_length=80)
    color = models.CharField(_("colour"), max_length=7, default="#F97316")
    destination = _destination()
    printer_usage = _printer_usage()
    #: A given printer of Printing, by its name; empty = the printer of the function.
    printer_name = models.CharField(_("printer"), max_length=100, blank=True)
    sort_order = models.PositiveIntegerField(_("position"), default=0)
    is_active = models.BooleanField(pgettext_lazy("kitchen", "active"), default=True)
    is_deleted = models.BooleanField(pgettext_lazy("kitchen station", "deleted"), default=False)
    deleted_at = models.DateTimeField(pgettext_lazy("kitchen station", "deleted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("station")
        verbose_name_plural = _("stations")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_deleted=False),
                name="kitchen_station_live_name",
            ),
            models.CheckConstraint(
                condition=_in("destination", Destination),
                name="kitchen_station_destination",
            ),
            models.CheckConstraint(
                condition=_in("printer_usage", PrinterUsage),
                name="kitchen_station_usage",
            ),
            models.CheckConstraint(
                condition=Q(color__regex=COLOR_RE), name="kitchen_station_color"
            ),
        ]

    def __str__(self) -> str:
        return self.name
