"""What happened in the kitchen: the History."""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.kitchen.models.fields import ACTOR_MAX_LENGTH, _in
from apps.kitchen.models.stations import Station
from apps.kitchen.models.tickets import Ticket, TicketItem


class LogAction(models.TextChoices):
    RECEIVED = "received", _("Received")
    CREATED = "created", _("Created")
    STARTED = "started", _("Fired")
    READY = "ready", _("Ready")
    ITEM_READY = "item_ready", _("Dish ready")
    ITEM_RECALLED = "item_recalled", _("Dish recalled")
    ITEM_VOIDED = "item_voided", _("Dish voided")
    SERVED = "served", _("Served")
    RECALLED = "recalled", _("Recalled")
    CANCELLED = "cancelled", _("Cancelled")
    RUSHED = "rushed", _("Rush")
    UNRUSHED = "unrushed", _("Rush removed")
    REPRINTED = "reprinted", _("Reprinted")
    DELETED = "deleted", _("Deleted")


class LogEntry(UUIDModel):
    """One thing that happened in the kitchen (the History)."""

    Action = LogAction

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="log", verbose_name=_("ticket")
    )
    item = models.ForeignKey(
        TicketItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("dish"),
    )
    station = models.ForeignKey(
        Station,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("station"),
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    actor = models.CharField(_("who"), max_length=ACTOR_MAX_LENGTH, blank=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("when"), default=timezone.now)

    class Meta:
        verbose_name = _("history entry")
        verbose_name_plural = _("history")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="kitchen_log_recent_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=_in("action", LogAction), name="kitchen_log_action"
            )
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.ticket.number}"
