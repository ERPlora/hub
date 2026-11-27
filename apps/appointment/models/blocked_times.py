"""The blocked times: periods nobody books, for the whole business or one professional."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.appointment.models.settings import ACTOR_MAX_LENGTH


class BlockedTime(UUIDModel):
    """A period nobody books: the whole business (no professional) or one professional."""

    class BlockType(models.TextChoices):
        HOLIDAY = "holiday", _("Holiday")
        VACATION = "vacation", _("Vacation")
        BREAK = "break", _("Break")
        MAINTENANCE = "maintenance", _("Maintenance")
        OTHER = "other", pgettext_lazy("blocked time type", "Other")

    title = models.CharField(_("title"), max_length=200)
    block_type = models.CharField(
        _("type"), max_length=12, choices=BlockType.choices, default=BlockType.OTHER
    )
    # A whole-day block is stored from the first day's midnight to the midnight after the last one.
    start = models.DateTimeField(_("starts at"))
    end = models.DateTimeField(_("ends at"))
    all_day = models.BooleanField(_("all day"), default=False)
    staff = models.ForeignKey(
        "staff.Member",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("professional"),
    )
    reason = models.CharField(_("reason"), max_length=500, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("blocked time")
        verbose_name_plural = _("blocked times")
        ordering = ["start", "id"]
        indexes = [
            models.Index(fields=["start", "end"], name="appointment_block_span_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gt=F("start")),
                name="appointment_block_ends_after_start",
            ),
            models.CheckConstraint(
                condition=Q(
                    block_type__in=[
                        "holiday",
                        "vacation",
                        "break",
                        "maintenance",
                        "other",
                    ]
                ),
                name="appointment_block_type",
            ),
        ]

    def __str__(self) -> str:
        return self.title
