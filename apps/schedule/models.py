"""Models of the schedule app: the usual week, the special days, the temporary changes and the settings.

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications are
per scope. Phase 2 moves them to each hub's database. Every row is really deleted (no soft delete): a
special day deleted frees its date. The rules about a set of intervals (sorted, never overlapping, at
most twelve) are engine.py's and the services', which write them; the database keeps what it can.
"""

import datetime as dt

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

#: Monday = 0, as ``datetime.date.weekday()``. With a context: Django's own catalogue spells them in
#: lowercase («lunes»), and a list of days starts with a capital.
WEEKDAY_NAMES = (
    pgettext_lazy("weekday", "Monday"),
    pgettext_lazy("weekday", "Tuesday"),
    pgettext_lazy("weekday", "Wednesday"),
    pgettext_lazy("weekday", "Thursday"),
    pgettext_lazy("weekday", "Friday"),
    pgettext_lazy("weekday", "Saturday"),
    pgettext_lazy("weekday", "Sunday"),
)
_MIDNIGHT = dt.time(0, 0)


class IntervalBase(UUIDModel):
    """One opening interval: ``close_time`` ≤ ``open_time`` crosses midnight, 00:00–00:00 is 24 hours."""

    position = models.PositiveSmallIntegerField(_("position"), default=0)
    open_time = models.TimeField(_("opens"))
    close_time = models.TimeField(_("closes"))

    class Meta:
        abstract = True
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.open_time:%H:%M}–{self.close_time:%H:%M}"


def _not_empty(prefix: str) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=~Q(open_time=F("close_time"))
        | Q(open_time=_MIDNIGHT, close_time=_MIDNIGHT),
        name=f"{prefix}_not_empty",
    )


class WeekDay(UUIDModel):
    """A day of the usual week (Monday = 0): closed, or open in its intervals. No row = not set."""

    weekday = models.PositiveSmallIntegerField(_("weekday"), unique=True)
    is_closed = models.BooleanField(_("closed"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("weekday")
        verbose_name_plural = _("usual week")
        ordering = ["weekday"]
        constraints = [
            models.CheckConstraint(
                condition=Q(weekday__lte=6), name="schedule_weekday_range"
            )
        ]

    def __str__(self) -> str:
        return (
            str(WEEKDAY_NAMES[self.weekday])
            if 0 <= self.weekday <= 6
            else str(self.weekday)
        )


class WeekDayInterval(IntervalBase):
    day = models.ForeignKey(
        WeekDay,
        on_delete=models.CASCADE,
        related_name="intervals",
        verbose_name=_("weekday"),
    )

    class Meta(IntervalBase.Meta):
        verbose_name = _("opening interval")
        verbose_name_plural = _("opening intervals")
        constraints = [
            models.UniqueConstraint(
                fields=["day", "position"], name="schedule_weekday_interval_position"
            ),
            _not_empty("schedule_weekday_interval"),
        ]


class SpecialDay(UUIDModel):
    """A date with other hours or closed (a holiday); yearly = the same day and month every year."""

    date = models.DateField(_("date"))
    name = models.CharField(_("name"), max_length=200)
    is_closed = models.BooleanField(_("closed"), default=True)
    recurring_yearly = models.BooleanField(_("repeats every year"), default=False)
    notes = models.TextField(_("notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("special day")
        verbose_name_plural = _("special days")
        ordering = ["date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["date"], name="schedule_special_day_date_unique"),
            models.CheckConstraint(condition=~Q(name=""), name="schedule_special_day_named"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.date:%Y-%m-%d})"


class SpecialDayInterval(IntervalBase):
    special_day = models.ForeignKey(
        SpecialDay,
        on_delete=models.CASCADE,
        related_name="intervals",
        verbose_name=_("special day"),
    )

    class Meta(IntervalBase.Meta):
        verbose_name = _("opening interval")
        verbose_name_plural = _("opening intervals")
        constraints = [
            models.UniqueConstraint(
                fields=["special_day", "position"],
                name="schedule_special_day_interval_position",
            ),
            _not_empty("schedule_special_day_interval"),
        ]


class Override(UUIDModel):
    """A temporary change: every day from ``start_date`` to ``end_date`` (both included) closed or with
    the same hours. Two of them never cover the same day (services.py)."""

    start_date = models.DateField(_("from"))
    end_date = models.DateField(_("to"))
    reason = models.CharField(_("reason"), max_length=200)
    is_closed = models.BooleanField(_("closed"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("temporary change")
        verbose_name_plural = _("temporary changes")
        ordering = ["start_date", "id"]
        indexes = [
            models.Index(
                fields=["start_date", "end_date"], name="schedule_override_range_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="schedule_override_range",
            ),
            models.CheckConstraint(
                condition=~Q(reason=""), name="schedule_override_reason"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reason} ({self.start_date:%Y-%m-%d} – {self.end_date:%Y-%m-%d})"


class OverrideInterval(IntervalBase):
    override = models.ForeignKey(
        Override,
        on_delete=models.CASCADE,
        related_name="intervals",
        verbose_name=_("temporary change"),
    )

    class Meta(IntervalBase.Meta):
        verbose_name = _("opening interval")
        verbose_name_plural = _("opening intervals")
        constraints = [
            models.UniqueConstraint(
                fields=["override", "position"],
                name="schedule_override_interval_position",
            ),
            _not_empty("schedule_override_interval"),
        ]


class ScheduleSettings(UUIDModel):
    """The settings of the schedule app: one row. ``hours_confirmed`` turns off the «default week» notice:
    somebody saved a day or confirmed the week."""

    slot = models.PositiveSmallIntegerField(_("slot"), default=1, editable=False)
    #: 1 = Monday … 7 = Sunday (ISO): only the order of the week's table.
    week_starts_on = models.PositiveSmallIntegerField(_("week starts on"), default=1)
    hours_confirmed = models.BooleanField(_("hours confirmed"), default=False)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("schedule settings")
        verbose_name_plural = _("schedule settings")
        constraints = [
            models.UniqueConstraint(
                fields=["slot"], name="schedule_settings_singleton"
            ),
            models.CheckConstraint(condition=Q(slot=1), name="schedule_settings_slot"),
            models.CheckConstraint(
                condition=Q(week_starts_on__gte=1, week_starts_on__lte=7),
                name="schedule_settings_week_start",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)
