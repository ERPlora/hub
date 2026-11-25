"""The record of what a manager may approve (``base.approvals``): their approvals, and what was done without needing one."""

from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from base.models.access import ACTOR_MAX_LENGTH


class Approval(UUIDModel):
    """One command a manager may approve: their approval of it once refused, given with their PIN or badge, or the command
    done by whoever may do it themselves (``way`` is ``ROLE``: no pass, no limit in time and nobody who approved it).

    The pass handed back is kept as its SHA-256 only, and works once, until ``expires_at``, for the person who asked
    (``requested_by``), that command (``operation``) and that very request of this business (``fingerprint``,
    ``base.approvals.fingerprint``). The names are kept as they were then: the record still reads when a person left.
    When the command is done, the figures of it that its app's sentences name (``figures``, JSON; none before, or for a
    command said without figures), so the record says «a 50 % discount». Nobody edits or deletes a row.
    """

    class Way(models.TextChoices):
        PIN = "pin", pgettext_lazy("way in", "PIN")
        BADGE = "badge", pgettext_lazy("way in", "Badge")
        ROLE = "role", pgettext_lazy("approval", "Their role")

    operation = models.CharField(pgettext_lazy("approval", "action"), max_length=120)
    permission = models.CharField(pgettext_lazy("approval", "permission"), max_length=120)
    fingerprint = models.CharField(pgettext_lazy("approval", "request fingerprint"), max_length=64)
    token_digest = models.CharField(pgettext_lazy("approval", "pass digest"), max_length=64, unique=True, null=True, blank=True)
    requested_by = models.CharField(pgettext_lazy("approval", "asked by"), max_length=ACTOR_MAX_LENGTH)
    requested_by_name = models.CharField(pgettext_lazy("approval", "asked by (name)"), max_length=ACTOR_MAX_LENGTH)
    approved_by = models.CharField(pgettext_lazy("approval", "approved by"), max_length=ACTOR_MAX_LENGTH)
    approved_by_name = models.CharField(pgettext_lazy("approval", "approved by (name)"), max_length=ACTOR_MAX_LENGTH)
    way = models.CharField(pgettext_lazy("approval", "approved with"), max_length=8, choices=Way.choices)
    created_at = models.DateTimeField(pgettext_lazy("approval", "approved at"), auto_now_add=True)
    expires_at = models.DateTimeField(pgettext_lazy("approval", "valid until"), null=True, blank=True)
    used_at = models.DateTimeField(pgettext_lazy("approval", "used at"), null=True, blank=True)
    figures = models.JSONField(pgettext_lazy("approval", "figures"), null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("approval", "approval")
        verbose_name_plural = pgettext_lazy("approval", "approvals")
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=Q(way__in=["pin", "badge", "role"]), name="base_approval_way")]

    def __str__(self) -> str:
        return f"{self.operation} · {self.approved_by_name or self.requested_by_name}"
