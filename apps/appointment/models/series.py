"""The repeating bookings: a series with its rule and its services in order."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.appointment.models.audit import Audited
from apps.appointment.models.settings import MAX_MINUTES
from base.weekdays import weekdays


class Recurring(Audited):
    """A repeating booking: who, what, with whom and its rule; each date it books is an appointment."""

    class Frequency(models.TextChoices):
        DAILY = "daily", _("Every day")
        WEEKLY = "weekly", _("Every week")
        BIWEEKLY = "biweekly", _("Every two weeks")
        MONTHLY = "monthly", _("Every month")

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("customer"),
    )
    customer_name = models.CharField(_("customer's name"), max_length=200, blank=True)
    # Empty when its professional left (the series is paused until somebody takes it over).
    staff = models.ForeignKey(
        "staff.Member",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("professional"),
    )
    staff_name = models.CharField(_("professional's name"), max_length=201, blank=True)
    frequency = models.CharField(_("repeats"), max_length=10, choices=Frequency.choices)
    # Monday = 0; weekly and biweekly only (the start date's weekday when empty).
    day_of_week = models.PositiveSmallIntegerField(_("day of the week"), null=True, blank=True, choices=weekdays)
    time = models.TimeField(_("time"))
    duration_minutes = models.PositiveIntegerField(_("duration (min)"))
    start_date = models.DateField(_("starts on"))
    end_date = models.DateField(_("ends on"), null=True, blank=True)
    max_occurrences = models.PositiveIntegerField(
        _("number of appointments"), null=True, blank=True
    )
    # Own context: a series is «activa», not Django's «activo» of the same English (hub#633).
    is_active = models.BooleanField(
        pgettext_lazy("appointment", "active"), default=True
    )
    # The series this one continues after an edit «from this occurrence on».
    split_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("split from"),
    )

    class Meta:
        verbose_name = _("repeating appointment")
        verbose_name_plural = _("repeating appointments")
        ordering = ["customer_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(frequency__in=["daily", "weekly", "biweekly", "monthly"]),
                name="appointment_recurring_frequency",
            ),
            models.CheckConstraint(
                condition=Q(day_of_week__isnull=True) | Q(day_of_week__lte=6),
                name="appointment_recurring_day_of_week",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="appointment_recurring_dates",
            ),
            models.CheckConstraint(
                condition=Q(max_occurrences__isnull=True) | Q(max_occurrences__gte=1),
                name="appointment_recurring_occurrences",
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1, duration_minutes__lte=MAX_MINUTES),
                name="appointment_recurring_duration",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer_name} · {self.get_frequency_display()}"


class RecurringService(UUIDModel):
    """A service of a series, in order; its price and length are read from the catalog at each booking."""

    recurring = models.ForeignKey(
        Recurring,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("series"),
    )
    service = models.ForeignKey(
        "service.Service",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("service"),
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("service of a series")
        verbose_name_plural = _("services of a series")
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recurring", "position"],
                name="appointment_recurring_line_position",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recurring_id} #{self.position}"
