"""Each app's delivery of an outbox event (``base.relay``)."""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class EventDelivery(UUIDModel):
    """One app's delivery of one outbox event (``base.relay``; the old Hub's ``_event_delivery``).

    The relay writes one row per app that listens to the event, when it takes the event (and marks the event's
    ``delivered_at``); the reaction's writes and its row's ``delivered`` commit in one transaction, so an app
    never gets an event twice. A reaction that fails waits a little longer each time (``next_attempt_at``) and,
    after its last attempt or past the deepest level of events an event can start (``depth``), stays ``dead``
    with what went wrong. It lives in each hub's database, beside its outbox.

    Who runs the business sees the ones given up in System › Failed events: resending one puts it back
    ``pending``; discarding it closes it for good (``discarded``), with who, when and why, and keeps the row.
    """

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("event delivery status", "Pending")
        DELIVERED = "delivered", pgettext_lazy("event delivery status", "Delivered")
        DEAD = "dead", pgettext_lazy("event delivery status", "Given up")
        DISCARDED = "discarded", pgettext_lazy("event delivery status", "Discarded")

    event = models.ForeignKey(
        "live.OutboxEvent",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=pgettext_lazy("event delivery", "event"),
    )
    app_label = models.CharField(_("app"), max_length=100)
    depth = models.PositiveSmallIntegerField(_("depth"), default=0)
    status = models.CharField(_("status"), max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)
    next_attempt_at = models.DateTimeField(_("next attempt"))
    last_error = models.TextField(_("last error"), blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    closed_at = models.DateTimeField(_("discarded at"), null=True, blank=True)
    closed_by = models.CharField(_("discarded by"), max_length=128, blank=True, db_default="")
    close_reason = models.CharField(_("why it was discarded"), max_length=500, blank=True, db_default="")

    class Meta:
        verbose_name = _("event delivery")
        verbose_name_plural = _("event deliveries")
        ordering = ["next_attempt_at", "app_label"]
        constraints = [
            models.UniqueConstraint(fields=["event", "app_label"], name="base_eventdelivery_event_app_unique")
        ]
        indexes = [
            models.Index(
                fields=["next_attempt_at"], condition=Q(status="pending"), name="base_eventdelivery_due"
            )
        ]

    def __str__(self) -> str:
        return f"{self.event_id} → {self.app_label} ({self.status})"
