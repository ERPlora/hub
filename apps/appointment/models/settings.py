"""The business's booking rules, and the limits every model of the app keeps: the length of the «by whom»
fields and the longest a booking lasts."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
#: The longest a booking lasts (a day), and a slot interval.
MAX_MINUTES = 1440


class Settings(UUIDModel):
    """The business's booking rules: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    default_duration = models.PositiveIntegerField(
        _("default duration (min)"), default=60
    )
    # The customer's window: the front desk always books for right now.
    min_booking_notice = models.PositiveIntegerField(
        _("minimum booking notice (min)"), default=60
    )
    # 0 = no limit.
    max_advance_booking = models.PositiveIntegerField(
        _("maximum advance booking (days)"), default=90
    )
    # The front desk is warned and may book anyway (Fresha, Vagaro, Mangomint, Timely); off = a hard
    # block. The customer never overlaps.
    allow_overlapping = models.BooleanField(
        _("allow overlapping appointments"), default=True
    )
    allow_customer_cancellation = models.BooleanField(
        _("customers may cancel"), default=True
    )
    cancellation_notice_hours = models.PositiveIntegerField(
        _("cancellation notice (hours)"), default=24
    )
    calendar_start_hour = models.PositiveSmallIntegerField(
        _("calendar starts at (hour)"), default=8
    )
    calendar_end_hour = models.PositiveSmallIntegerField(
        _("calendar ends at (hour)"), default=20
    )
    slot_interval = models.PositiveIntegerField(_("slot interval (min)"), default=15)
    auto_confirm_online = models.BooleanField(
        _("confirm the customer's bookings automatically"), default=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("appointment settings")
        verbose_name_plural = _("appointment settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="appointment_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="appointment_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(calendar_start_hour__lt=F("calendar_end_hour"))
                & Q(calendar_end_hour__lte=24),
                name="appointment_settings_calendar_window",
            ),
            models.CheckConstraint(
                condition=Q(default_duration__gte=1, slot_interval__gte=1),
                name="appointment_settings_minutes",
            ),
        ]

    def __str__(self) -> str:
        return str(_("Appointment settings"))
