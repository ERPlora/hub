"""Models of the staff app: roles, the record of each professional, their schedules and time off.

Phase 1 has no tenancy: every scope (``a``, ``b``) shares these tables; only the live notifications
are per scope. Phase 2 moves them to each hub's database. The record hangs from the platform's user
(``settings.AUTH_USER_MODEL``) like ``base.Membership``; phase 2 moves both links to the hub's users.
"""

import datetime as dt

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel


class Role(UUIDModel):
    """A role of the business's catalogue («stylist», «waiter»): a label, never a permission."""

    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    color = models.CharField(_("colour"), max_length=7, blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="staff_role_name_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Member(UUIDModel):
    """The record of a person who works in the business; ``terminated`` is its soft delete."""

    # Short labels carry a context: Django merges the apps' catalogues, and another app may translate
    # the same word otherwise («Other» → «Otro»).
    class Status(models.TextChoices):
        ACTIVE = "active", pgettext_lazy("staff member status", "Active")
        INACTIVE = "inactive", pgettext_lazy("staff member status", "Inactive")
        ON_LEAVE = "on_leave", pgettext_lazy("staff member status", "On leave")
        TERMINATED = "terminated", pgettext_lazy("staff member status", "Terminated")

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("last name"), max_length=100)
    email = models.EmailField(_("email"), max_length=254, blank=True)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    employee_number = models.CharField(_("employee number"), max_length=50, blank=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name=_("role"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members",
        verbose_name=_("user"),
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    is_bookable = models.BooleanField(_("bookable"), default=True)
    booking_buffer = models.PositiveSmallIntegerField(
        _("minutes between appointments"), default=0
    )
    hire_date = models.DateField(_("hire date"), null=True, blank=True)
    termination_date = models.DateField(_("last day"), null=True, blank=True)
    termination_reason = models.CharField(
        _("reason for leaving"), max_length=500, blank=True
    )
    color = models.CharField(_("colour"), max_length=7, blank=True)
    specialties = models.TextField(_("specialties"), blank=True)
    bio = models.TextField(_("bio"), blank=True)
    # Money in whole cents, never negative; the commission is a percentage, not money.
    hourly_rate = models.PositiveIntegerField(_("hourly rate (cents)"), default=0)
    commission_rate = models.DecimalField(
        _("commission (%)"), max_digits=5, decimal_places=2, default=0
    )
    # HR notes: private, shown only with the pay (staff.member.compensation).
    notes = models.TextField(_("HR notes"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("staff member")
        verbose_name_plural = _("staff members")
        # The order of staff.member.list: by name, id as the tie-break.
        ordering = ["first_name", "last_name", "id"]
        indexes = [
            models.Index(
                fields=["status", "first_name", "last_name", "id"],
                name="staff_member_status_name_idx",
            )
        ]
        constraints = [
            # One user, one live record: a terminated record frees its user.
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(user__isnull=False) & ~Q(status="terminated"),
                name="staff_member_user_unique",
            ),
            models.CheckConstraint(
                condition=Q(commission_rate__gte=0) & Q(commission_rate__lte=100),
                name="staff_member_commission_range",
            ),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Schedule(UUIDModel):
    """A weekly schedule of a member, valid between two optional dates."""

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("staff member"),
    )
    name = models.CharField(_("name"), max_length=100)
    is_default = models.BooleanField(_("default"), default=True)
    effective_from = models.DateField(_("valid from"), null=True, blank=True)
    effective_until = models.DateField(_("valid until"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("schedule")
        verbose_name_plural = _("schedules")
        ordering = ["-is_default", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["member"],
                condition=Q(is_default=True),
                name="staff_schedule_one_default",
            ),
            models.CheckConstraint(
                condition=Q(effective_from__isnull=True)
                | Q(effective_until__isnull=True)
                | Q(effective_until__gte=F("effective_from")),
                name="staff_schedule_valid_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ScheduleDay(UUIDModel):
    """The working hours of one weekday (Monday = 0) of a schedule; a missing day is a day off."""

    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name="days",
        verbose_name=_("schedule"),
    )
    weekday = models.PositiveSmallIntegerField(_("weekday"))
    start_time = models.TimeField(_("start"))
    end_time = models.TimeField(_("end"))
    break_start = models.TimeField(_("break start"), null=True, blank=True)
    break_end = models.TimeField(_("break end"), null=True, blank=True)

    class Meta:
        verbose_name = _("working day")
        verbose_name_plural = _("working days")
        ordering = ["weekday", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "weekday"], name="staff_schedule_day_unique"
            ),
            models.CheckConstraint(
                condition=Q(weekday__lte=6), name="staff_schedule_day_weekday"
            ),
            models.CheckConstraint(
                condition=Q(start_time__lt=F("end_time")),
                name="staff_schedule_day_order",
            ),
            models.CheckConstraint(
                condition=Q(break_start__isnull=True, break_end__isnull=True)
                | Q(
                    # Explicit: a CHECK that evaluates to NULL passes, so one end alone must be false.
                    break_start__isnull=False,
                    break_end__isnull=False,
                    break_start__gte=F("start_time"),
                    break_start__lt=F("break_end"),
                    break_end__lte=F("end_time"),
                ),
                name="staff_schedule_day_break",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weekday}: {self.start_time}–{self.end_time}"


class TimeOff(UUIDModel):
    """An absence of a member: whole days, or the same hours on each day of its range."""

    class LeaveType(models.TextChoices):
        VACATION = "vacation", pgettext_lazy("leave type", "Vacation")
        SICK = "sick", pgettext_lazy("leave type", "Sick leave")
        PERSONAL = "personal", pgettext_lazy("leave type", "Personal")
        TRAINING = "training", pgettext_lazy("leave type", "Training")
        OTHER = "other", pgettext_lazy("leave type", "Other")

    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("time-off status", "Pending")
        APPROVED = "approved", pgettext_lazy("time-off status", "Approved")
        REJECTED = "rejected", pgettext_lazy("time-off status", "Rejected")
        CANCELLED = "cancelled", pgettext_lazy("time-off status", "Cancelled")

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="time_off",
        verbose_name=_("staff member"),
    )
    leave_type = models.CharField(
        _("type"), max_length=10, choices=LeaveType.choices, default=LeaveType.VACATION
    )
    start_date = models.DateField(_("from"))
    end_date = models.DateField(_("until"))
    is_full_day = models.BooleanField(_("full day"), default=True)
    start_time = models.TimeField(_("from (time)"), null=True, blank=True)
    end_time = models.TimeField(_("until (time)"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    reason = models.CharField(_("reason"), max_length=500, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("approved by"),
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("time off")
        verbose_name_plural = _("time off")
        # The order of staff.time_off.list: the most recent first, id as the tie-break.
        ordering = ["-start_date", "id"]
        indexes = [
            models.Index(
                fields=["member", "status", "start_date"],
                name="staff_time_off_member_idx",
            ),
            models.Index(
                fields=["status", "start_date", "end_date"],
                name="staff_time_off_status_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="staff_time_off_dates"
            ),
            models.CheckConstraint(
                condition=Q(
                    is_full_day=True, start_time__isnull=True, end_time__isnull=True
                )
                | Q(
                    is_full_day=False,
                    start_time__isnull=False,
                    end_time__isnull=False,
                    start_time__lt=F("end_time"),
                ),
                name="staff_time_off_times",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member} {self.start_date}–{self.end_date}"


class StaffSettings(UUIDModel):
    """The settings of the staff app: one row, created by the first save (until then, the defaults).

    The eleven settings of the old module, with its defaults and ranges. None of them changes how
    Staff, Appointments or the till behave yet: they are kept for the screens that will read them.
    """

    slot = models.PositiveSmallIntegerField(_("slot"), default=1, editable=False)
    default_work_start = models.TimeField(_("working day starts"), default=dt.time(9))
    default_work_end = models.TimeField(_("working day ends"), default=dt.time(18))
    default_break_duration = models.PositiveSmallIntegerField(
        _("break duration (minutes)"), default=60
    )
    min_advance_booking = models.PositiveSmallIntegerField(
        _("minimum booking notice (hours)"), default=1
    )
    max_daily_hours = models.PositiveSmallIntegerField(
        _("maximum hours per day"), default=12
    )
    overtime_threshold = models.PositiveSmallIntegerField(
        _("overtime threshold (hours/week)"), default=40
    )
    show_staff_photos = models.BooleanField(_("show staff photos"), default=True)
    show_staff_bio = models.BooleanField(_("show staff bio"), default=True)
    allow_staff_selection = models.BooleanField(
        _("let customers choose the professional"), default=True
    )
    notify_new_appointment = models.BooleanField(
        _("notify on a new appointment"), default=True
    )
    notify_cancellation = models.BooleanField(
        _("notify on a cancellation"), default=True
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("staff settings")
        verbose_name_plural = _("staff settings")
        constraints = [
            models.UniqueConstraint(fields=["slot"], name="staff_settings_singleton"),
            models.CheckConstraint(condition=Q(slot=1), name="staff_settings_slot"),
            models.CheckConstraint(
                condition=Q(default_break_duration__lte=480)
                & Q(min_advance_booking__lte=168)
                & Q(max_daily_hours__gte=1, max_daily_hours__lte=24)
                & Q(overtime_threshold__gte=1, overtime_threshold__lte=168),
                name="staff_settings_ranges",
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)
