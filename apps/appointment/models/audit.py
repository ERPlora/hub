"""What an appointment and a series both keep: when each was created, changed and deleted, and who created it."""

from django.db import models
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.appointment.models.settings import ACTOR_MAX_LENGTH


class Audited(UUIDModel):
    """When an appointment or a series was created, changed and deleted, and who created it.

    Its own context, as a «cita»: «borrada», «creada» and «actualizada», not the «eliminado» or «creado» other apps
    say for the same English (hub#633)."""

    deleted_at = models.DateTimeField(
        pgettext_lazy("appointment", "deleted at"), null=True, blank=True
    )
    created_at = models.DateTimeField(
        pgettext_lazy("appointment", "created at"), auto_now_add=True
    )
    updated_at = models.DateTimeField(
        pgettext_lazy("appointment", "updated at"), auto_now=True
    )
    created_by = models.CharField(
        pgettext_lazy("appointment", "created by"),
        max_length=ACTOR_MAX_LENGTH,
        blank=True,
    )

    class Meta:
        abstract = True
