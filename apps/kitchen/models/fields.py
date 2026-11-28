"""What the kitchen app's models share: closed lists, where a dish goes and who made and changed a row."""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128


class Destination(models.TextChoices):
    BOTH = "both", _("Screen and paper")
    DISPLAY = "display", _("Screen only")
    PRINTER = "printer", _("Paper only")


class PrinterUsage(models.TextChoices):
    KITCHEN = "kitchen", _("Kitchen")
    BAR = "bar", _("Bar")


class OrderType(models.TextChoices):
    DINE_IN = "dine_in", _("Dine in")
    TAKEAWAY = "takeaway", _("Takeaway")
    DELIVERY = "delivery", _("Delivery")


def _in(field: str, choices) -> Q:
    return Q(**{f"{field}__in": choices.values})


def _destination() -> models.CharField:
    return models.CharField(_("destination"), max_length=8, choices=Destination.choices, default=Destination.BOTH)


def _printer_usage() -> models.CharField:
    return models.CharField(_("printer function"), max_length=8, choices=PrinterUsage.choices, default=PrinterUsage.KITCHEN)


class Audited(UUIDModel):
    """Who created and last changed a row, and when."""

    created_at = models.DateTimeField(
        _("created at"), default=timezone.now, editable=False
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        abstract = True
