"""What each hub used and did, day by day, and the nights it was measured."""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from control.models.hubs import Hub


class HubUsageDaily(UUIDModel):
    """What a hub with its own database used on a day (UTC), as the worker measured it that night (``base.usage``):
    its database (``pg_database_size``), its files in S3 and the people who came in that day and in the 30 days that
    end it. One row per hub and day; ``GET /internal/usage?day=`` serves them to the SaaS (its ``hubs/README.md``,
    «Contrato para el Hub»)."""

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="usage", verbose_name=_("hub"))
    day = models.DateField(pgettext_lazy("hub usage", "day"))
    db_bytes = models.PositiveBigIntegerField(_("database (bytes)"), default=0)
    s3_bytes = models.PositiveBigIntegerField(_("files (bytes)"), default=0)
    active_users_1d = models.PositiveIntegerField(_("people that day"), default=0)
    active_users_30d = models.PositiveIntegerField(_("people in 30 days"), default=0)
    measured_at = models.DateTimeField(pgettext_lazy("hub usage", "measured at"))

    class Meta:
        verbose_name = _("daily use of a hub")
        verbose_name_plural = _("daily use of the hubs")
        ordering = ["-day", "hub_id"]
        constraints = [models.UniqueConstraint(fields=["hub", "day"], name="control_hubusagedaily_one_per_day")]
        indexes = [models.Index(fields=["day", "hub"], name="control_hubusagedaily_day_hub")]

    def __str__(self) -> str:
        return f"{self.hub_id} @ {self.day}"


class HubActivityDaily(UUIDModel):
    """What a hub did on a day (UTC), as its serving tasks counted it (``base.meter``, every minute): the requests it
    served, the most transactions it had at once in one process (how the plan's limit is applied) and the requests
    that found no room (503 ``base.hub_busy``). One row per hub and day, added to by every task with atomic increments;
    ``GET /internal/usage?day=`` serves it to the SaaS with that night's figures (``HubUsageDaily``)."""

    hub = models.ForeignKey(Hub, on_delete=models.CASCADE, related_name="activity", verbose_name=_("hub"))
    day = models.DateField(pgettext_lazy("hub usage", "day"))
    requests = models.PositiveBigIntegerField(_("requests"), default=0)
    peak_connections = models.PositiveIntegerField(_("most connections at once"), default=0)
    busy_requests = models.PositiveBigIntegerField(_("requests with no room"), default=0)

    class Meta:
        verbose_name = _("daily activity of a hub")
        verbose_name_plural = _("daily activity of the hubs")
        ordering = ["-day", "hub_id"]
        constraints = [models.UniqueConstraint(fields=["hub", "day"], name="control_hubactivitydaily_one_per_day")]

    def __str__(self) -> str:
        return f"{self.hub_id} @ {self.day}"


class HubVisit(models.Model):
    """A person had activity in a hub on a day (UTC): a login of their account, their PIN or their badge
    (``base.services``, every login) or anything they did there since (``base.meter``), so a session open for days
    counts on each of them. One row per hub, day and person: what the nightly measurement counts as the hub's active
    people (``base.usage``), which keeps the last 31 days only. ``last_seen_at`` says who has activity now (empty: a
    login not followed by anything yet, or a row from before it was noted)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    host = models.CharField(pgettext_lazy("hub usage", "host"), max_length=63)
    day = models.DateField(pgettext_lazy("hub usage", "day"))
    saas_user_id = models.CharField(pgettext_lazy("hub usage", "SaaS account"), max_length=64)
    last_seen_at = models.DateTimeField(pgettext_lazy("hub usage", "last seen at"), null=True, blank=True)

    class Meta:
        verbose_name = _("daily entry")
        verbose_name_plural = _("daily entries")
        constraints = [
            models.UniqueConstraint(fields=["host", "day", "saas_user_id"], name="control_hubvisit_one_per_day")
        ]

    def __str__(self) -> str:
        return f"{self.saas_user_id} @ {self.host} ({self.day})"


class UsageRun(UUIDModel):
    """One night of measuring (``base.usage``): the day (UTC) measured, when a worker started it and when it finished.
    A day without a finished run is one the Hub has not measured yet (``GET /internal/usage`` answers 409
    ``usage_not_ready``); a run left unfinished (its worker stopped) is taken over after a while."""

    day = models.DateField(pgettext_lazy("hub usage", "day"), unique=True)
    started_at = models.DateTimeField(pgettext_lazy("hub usage", "started at"))
    finished_at = models.DateTimeField(pgettext_lazy("hub usage", "finished at"), null=True, blank=True)
    hubs = models.PositiveIntegerField(_("hubs measured"), default=0)

    class Meta:
        verbose_name = _("nightly measurement")
        verbose_name_plural = _("nightly measurements")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day}"
