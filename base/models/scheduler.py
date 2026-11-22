"""When each scheduled task of an app runs next (``base.scheduler``)."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel


class TaskSchedule(UUIDModel):
    """When a scheduled task of an app runs next (``base.scheduler``; the old Hub's ``_scheduled_tasks``).

    One row per task an app declares (``LiveAppConfig.scheduled_tasks``), written by the worker when it
    starts: the operation and the cron come from the code, the clock is the row's. It lives in each hub's database,
    beside the rest of the hub's business.
    """

    app_label = models.CharField(_("app"), max_length=100)
    name = models.CharField(_("name"), max_length=100)
    operation = models.CharField(_("operation"), max_length=200)
    cron = models.CharField(_("cron (UTC)"), max_length=100)
    next_run = models.DateTimeField(_("next run"))
    last_run = models.DateTimeField(_("last run"), null=True, blank=True)

    class Meta:
        verbose_name = _("scheduled task")
        verbose_name_plural = _("scheduled tasks")
        ordering = ["app_label", "name"]
        constraints = [
            models.UniqueConstraint(fields=["app_label", "name"], name="base_taskschedule_app_name_unique")
        ]
        indexes = [models.Index(fields=["next_run"], name="base_taskschedule_next_run")]

    def __str__(self) -> str:
        return f"{self.app_label}.{self.name}"
