"""Models of the attendance app: the working day, its breaks, the trail of its corrections and the
settings (WORKBOOK «Para quien lo mantiene»).

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications are
per scope. A working day belongs to a staff record (``staff.Member``, the app this one requires) and is
never deleted: the law asks for four years of records (art. 34.9 ET), so the foreign keys PROTECT and
there is no delete operation. Times are stored in UTC; ``work_date`` is the business day of the clock-in. Who
clocked, corrected or changed a day hangs from the person in the business's own database (``base.HubUser``), never
from control's user (tenancy W10): the columns ``*_hub_user_id`` are new, the old ones wait empty for a later deploy to
drop them (``migrations/0003_hub_users``).
"""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

#: The context of the model names other apps' catalogues also have («working day» is Staff's weekday of a schedule,
#: «slot» a schedule's slot): without it the Hub said them the other app's way («día de trabajo», «ranura»).
NAMES = "attendance"

#: The radii a personal device may be asked to be within (metres), as the old module.
RADII = (50, 100, 250, 500, 1000)


class Record(UUIDModel):
    """A working day of a person: a clock-in and, once over, a clock-out, with breaks inside."""

    # Short labels carry a context: Django merges the apps' catalogues, and another app may translate
    # the same word otherwise («Open» → «Abierto»).
    class Status(models.TextChoices):
        OPEN = "open", pgettext_lazy("working day status", "Open")
        CLOSED = "closed", pgettext_lazy("working day status", "Closed")
        NEEDS_REVIEW = (
            "needs_review",
            pgettext_lazy("working day status", "Needs review"),
        )

    class Source(models.TextChoices):
        SHARED = "shared", pgettext_lazy("clocking device", "Shared device")
        PERSONAL = "personal", pgettext_lazy("clocking device", "Personal device")

    member = models.ForeignKey(
        "staff.Member",
        on_delete=models.PROTECT,
        related_name="attendance_records",
        verbose_name=_("staff member"),
    )
    work_date = models.DateField(_("date"))
    clock_in_at = models.DateTimeField(_("clock-in"))
    clock_out_at = models.DateTimeField(_("clock-out"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.OPEN
    )
    source = models.CharField(
        _("device"), max_length=8, choices=Source.choices, default=Source.SHARED
    )
    # Where the day was clocked from: only when the device sent its position, and only at that moment.
    in_lat = models.FloatField(_("clock-in latitude"), null=True, blank=True)
    in_lng = models.FloatField(_("clock-in longitude"), null=True, blank=True)
    in_accuracy_m = models.FloatField(_("clock-in accuracy (m)"), null=True, blank=True)
    in_distance_m = models.FloatField(_("clock-in distance (m)"), null=True, blank=True)
    in_within_radius = models.BooleanField(
        _("clock-in within the radius"), null=True, blank=True
    )
    out_lat = models.FloatField(_("clock-out latitude"), null=True, blank=True)
    out_lng = models.FloatField(_("clock-out longitude"), null=True, blank=True)
    out_accuracy_m = models.FloatField(
        _("clock-out accuracy (m)"), null=True, blank=True
    )
    out_distance_m = models.FloatField(
        _("clock-out distance (m)"), null=True, blank=True
    )
    out_within_radius = models.BooleanField(
        _("clock-out within the radius"), null=True, blank=True
    )
    note = models.TextField(_("internal note"), blank=True)
    created_by = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="created_by_hub_user_id",
        verbose_name=_("clocked by"),
    )
    updated_by = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="updated_by_hub_user_id",
        verbose_name=_("last changed by"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy(NAMES, "working day")
        verbose_name_plural = pgettext_lazy(NAMES, "working days")
        # The order of attendance.record.list by default: the newest first, id as the tie-break.
        ordering = ["-clock_in_at", "id"]
        indexes = [
            models.Index(
                fields=["member", "clock_in_at"], name="attendance_record_member_idx"
            ),
            models.Index(fields=["work_date", "id"], name="attendance_record_date_idx"),
            models.Index(
                fields=["status", "clock_in_at"], name="attendance_record_status_idx"
            ),
        ]
        constraints = [
            # One OPEN working day per person: two taps at once leave one (the services lock the
            # person first; this is what still holds whatever door writes).
            models.UniqueConstraint(
                fields=["member"],
                condition=Q(status="open"),
                name="attendance_record_one_open",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["open", "closed", "needs_review"]),
                name="attendance_record_status",
            ),
            models.CheckConstraint(
                condition=Q(source__in=["shared", "personal"]),
                name="attendance_record_source",
            ),
            # Open and needs_review have no clock-out (nobody invents one); closed always has one.
            models.CheckConstraint(
                condition=Q(
                    status__in=["open", "needs_review"], clock_out_at__isnull=True
                )
                | Q(status="closed", clock_out_at__isnull=False),
                name="attendance_record_status_clock_out",
            ),
            models.CheckConstraint(
                condition=Q(clock_out_at__isnull=True)
                | Q(clock_out_at__gt=F("clock_in_at")),
                name="attendance_record_out_after_in",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member} · {self.work_date.isoformat()}"


class Break(UUIDModel):
    """A break inside a working day; ``ended_at`` stays empty while it runs."""

    record = models.ForeignKey(
        Record,
        on_delete=models.PROTECT,
        related_name="breaks",
        verbose_name=pgettext_lazy(NAMES, "working day"),
    )
    started_at = models.DateTimeField(_("started at"))
    ended_at = models.DateTimeField(pgettext_lazy(NAMES, "ended at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("break")
        verbose_name_plural = _("breaks")
        ordering = ["started_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["record"],
                condition=Q(ended_at__isnull=True),
                name="attendance_break_one_running",
            ),
            models.CheckConstraint(
                condition=Q(ended_at__isnull=True) | Q(ended_at__gte=F("started_at")),
                name="attendance_break_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.record} · {self.started_at.isoformat()}"


class Correction(UUIDModel):
    """The trail of a correction: the day before and after, the reason, who and when. Only inserted."""

    record = models.ForeignKey(
        Record,
        on_delete=models.PROTECT,
        related_name="corrections",
        verbose_name=pgettext_lazy(NAMES, "working day"),
    )
    old_clock_in_at = models.DateTimeField(_("clock-in before"))
    old_clock_out_at = models.DateTimeField(
        _("clock-out before"), null=True, blank=True
    )
    old_status = models.CharField(
        _("status before"), max_length=12, choices=Record.Status.choices
    )
    new_clock_in_at = models.DateTimeField(_("clock-in after"))
    new_clock_out_at = models.DateTimeField(_("clock-out after"), null=True, blank=True)
    new_status = models.CharField(
        _("status after"), max_length=12, choices=Record.Status.choices
    )
    reason = models.CharField(_("reason"), max_length=500)
    # The system made it (ATTENDANCE-F13: a termination closes the day). Said explicitly: a user deleted
    # later empties `created_by`, and that correction is still theirs, not the system's.
    is_system = models.BooleanField(_("made by the system"), default=False)
    created_by = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="created_by_hub_user_id",
        verbose_name=_("corrected by"),
    )
    # Who corrected, copied when the row is written: the trail keeps it even if the user goes.
    created_by_name = models.CharField(_("corrected by (name)"), max_length=300, blank=True)
    created_at = models.DateTimeField(_("corrected at"), auto_now_add=True)

    class Meta:
        verbose_name = _("correction")
        verbose_name_plural = _("corrections")
        # The order of the history: the most recent first.
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["record", "created_at"], name="attendance_correction_idx"
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.record} · {self.created_at.isoformat() if self.created_at else ''}"
        )


class AttendanceSettings(UUIDModel):
    """The settings of the time clock: one row, created by the first save (until then, the defaults)."""

    slot = models.PositiveSmallIntegerField(pgettext_lazy(NAMES, "slot"), default=1, editable=False)
    require_location = models.BooleanField(
        _("require the location when clocking in from a personal device"), default=False
    )
    geofence_radius_m = models.PositiveSmallIntegerField(
        _("allowed radius (m)"),
        default=100,
        choices=[(radius, f"{radius} m") for radius in RADII],
    )
    workplace_lat = models.FloatField(_("workplace latitude"), null=True, blank=True)
    workplace_lng = models.FloatField(_("workplace longitude"), null=True, blank=True)
    auto_close_after_hours = models.PositiveSmallIntegerField(
        _("flag open days for review after (hours)"), default=12
    )
    updated_by = models.ForeignKey(
        "base.HubUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_column="updated_by_hub_user_id",
        verbose_name=_("last changed by"),
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("time clock settings")
        verbose_name_plural = _("time clock settings")
        constraints = [
            models.UniqueConstraint(
                fields=["slot"], name="attendance_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(slot=1), name="attendance_settings_slot"
            ),
            models.CheckConstraint(
                condition=Q(geofence_radius_m__in=RADII),
                name="attendance_settings_radius",
            ),
            models.CheckConstraint(
                condition=Q(
                    auto_close_after_hours__gte=1, auto_close_after_hours__lte=24
                ),
                name="attendance_settings_hours",
            ),
            # The workplace is both coordinates, in range, or neither.
            models.CheckConstraint(
                condition=Q(workplace_lat__isnull=True, workplace_lng__isnull=True)
                | Q(
                    # Explicit: a CHECK that evaluates to NULL passes, so one end alone must be false.
                    workplace_lat__isnull=False,
                    workplace_lng__isnull=False,
                    workplace_lat__gte=-90,
                    workplace_lat__lte=90,
                    workplace_lng__gte=-180,
                    workplace_lng__lte=180,
                ),
                name="attendance_settings_workplace",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)
