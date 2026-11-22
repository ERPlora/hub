"""A manager's approval of one refused command, and its record (``base.approvals``)."""

from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from base.models.access import ACTOR_MAX_LENGTH


class Approval(UUIDModel):
    """A manager's approval of one refused command, given with their PIN or badge, and its record.

    The pass handed back is kept as its SHA-256 only, and works once, until ``expires_at``, for the person who asked
    (``requested_by``), that command (``operation``) and that very request of this business (``fingerprint``,
    ``base.approvals.fingerprint``). The names are kept as they were then: the record still reads when a person left.
    When the pass is spent, the figures of what it let through that its app's sentences name (``figures``, JSON; none
    before, or for a command said without figures), so the record says «a 50 % discount». Nobody edits or deletes a row.
    """

    class Way(models.TextChoices):
        PIN = "pin", pgettext_lazy("way in", "PIN")
        BADGE = "badge", pgettext_lazy("way in", "Badge")

    operation = models.CharField(pgettext_lazy("approval", "action"), max_length=120)
    permission = models.CharField(pgettext_lazy("approval", "permission"), max_length=120)
    fingerprint = models.CharField(pgettext_lazy("approval", "request fingerprint"), max_length=64)
    token_digest = models.CharField(pgettext_lazy("approval", "pass digest"), max_length=64, unique=True)
    requested_by = models.CharField(pgettext_lazy("approval", "asked by"), max_length=ACTOR_MAX_LENGTH)
    requested_by_name = models.CharField(pgettext_lazy("approval", "asked by (name)"), max_length=ACTOR_MAX_LENGTH)
    approved_by = models.CharField(pgettext_lazy("approval", "approved by"), max_length=ACTOR_MAX_LENGTH)
    approved_by_name = models.CharField(pgettext_lazy("approval", "approved by (name)"), max_length=ACTOR_MAX_LENGTH)
    way = models.CharField(pgettext_lazy("approval", "approved with"), max_length=8, choices=Way.choices)
    created_at = models.DateTimeField(pgettext_lazy("approval", "approved at"), auto_now_add=True)
    expires_at = models.DateTimeField(pgettext_lazy("approval", "valid until"))
    used_at = models.DateTimeField(pgettext_lazy("approval", "used at"), null=True, blank=True)
    figures = models.JSONField(pgettext_lazy("approval", "figures"), null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("approval", "approval")
        verbose_name_plural = pgettext_lazy("approval", "approvals")
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=Q(way__in=["pin", "badge"]), name="base_approval_way")]

    def __str__(self) -> str:
        return f"{self.operation} · {self.approved_by_name}"
