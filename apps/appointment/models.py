"""Models of the appointment app: the settings, the day counter of the numbers, the appointments with their
frozen service lines and their history, the blocked periods, and the repeating series.

Instants are stored with their zone (UTC) and read on the business's clock. An appointment copies what
it was booked with — the customer's name and contact, each service's name, price and length, the
professional's name — so that changing a card or the catalog later never rewrites what was booked.
Money is in cents. Deleting an appointment or a series is logical (``deleted_at``): what points at them
keeps pointing. Phase 1 has no tenancy: every scope shares these tables; phase 2 moves them to each
hub's database.
"""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
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


class Counter(UUIDModel):
    """The last number handed out on a business day (``APT-YYYYMMDD-NNNN``); never a sequence."""

    day = models.DateField(_("day"), unique=True)
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("appointment counter")
        verbose_name_plural = _("appointment counters")
        ordering = ["-day"]

    def __str__(self) -> str:
        return f"{self.day:%Y%m%d}: {self.last_number}"


class Recurring(UUIDModel):
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
    day_of_week = models.PositiveSmallIntegerField(
        _("day of the week"), null=True, blank=True
    )
    time = models.TimeField(_("time"))
    duration_minutes = models.PositiveIntegerField(_("duration (min)"))
    start_date = models.DateField(_("starts on"))
    end_date = models.DateField(_("ends on"), null=True, blank=True)
    max_occurrences = models.PositiveIntegerField(
        _("number of appointments"), null=True, blank=True
    )
    is_active = models.BooleanField(_("active"), default=True)
    # The series this one continues after an edit «from this occurrence on».
    split_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("split from"),
    )
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
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


class Appointment(UUIDModel):
    """A booking: a customer, one or more services and a professional at a time on the business's clock."""

    # Short labels carry a context: Django merges the apps' catalogues, and another app may translate
    # the same word otherwise («Pending» → «Pendiente» / «Pendiente de pago»).
    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("appointment status", "Pending")
        CONFIRMED = "confirmed", pgettext_lazy("appointment status", "Confirmed")
        IN_PROGRESS = "in_progress", pgettext_lazy("appointment status", "In progress")
        COMPLETED = "completed", pgettext_lazy("appointment status", "Completed")
        CANCELLED = "cancelled", pgettext_lazy("appointment status", "Cancelled")
        NO_SHOW = "no_show", pgettext_lazy("appointment status", "No-show")

    class Source(models.TextChoices):
        COUNTER = "counter", _("Front desk")
        PHONE = "phone", _("Phone")
        ONLINE = "online", _("Online booking")
        WHATSAPP = "whatsapp", _("WhatsApp")

    number = models.CharField(_("number"), max_length=24, unique=True)
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("customer"),
    )
    # Copies of the card at booking time (emptied when the customer's data is erased).
    customer_name = models.CharField(_("customer's name"), max_length=200, blank=True)
    customer_phone = models.CharField(_("customer's phone"), max_length=16, blank=True)
    customer_email = models.CharField(_("customer's email"), max_length=254, blank=True)
    # Empty = unassigned (its professional left: to be handed to somebody else).
    staff = models.ForeignKey(
        "staff.Member",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("professional"),
    )
    staff_name = models.CharField(_("professional's name"), max_length=201, blank=True)
    start = models.DateTimeField(_("starts at"))
    end = models.DateTimeField(_("ends at"))
    duration_minutes = models.PositiveIntegerField(_("duration (min)"))
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.CONFIRMED
    )
    source = models.CharField(
        _("booked through"),
        max_length=10,
        choices=Source.choices,
        default=Source.COUNTER,
    )
    # Visible to the customer; the internal one may hold health data (an allergy, a colour formula).
    notes = models.TextField(_("notes"), blank=True)
    internal_notes = models.TextField(_("internal notes"), blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancellation_reason = models.CharField(
        _("cancellation reason"), max_length=500, blank=True
    )
    cancelled_by_customer = models.BooleanField(
        _("cancelled by the customer"), default=False
    )
    # The sale of the till that charged it (an opaque id: Sales is not a requirement).
    sale_id = models.UUIDField(_("sale"), null=True, blank=True)
    # The check «Charge» opened in the till for it, while it is open: charging again goes back to it.
    order_id = models.UUIDField(_("open check"), null=True, blank=True)
    charged_at = models.DateTimeField(_("charged at"), null=True, blank=True)
    recurring = models.ForeignKey(
        Recurring,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
        verbose_name=_("series"),
    )
    # The wall-clock date the series generated: the occurrence's key, not where it ended up.
    occurrence_date = models.DateField(_("occurrence"), null=True, blank=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("appointment")
        verbose_name_plural = _("appointments")
        ordering = ["start", "id"]
        indexes = [
            models.Index(fields=["start", "id"], name="appointment_start_idx"),
            models.Index(fields=["staff", "start"], name="appointment_staff_start_idx"),
            models.Index(fields=["customer", "start"], name="appointment_customer_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gt=F("start")), name="appointment_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1, duration_minutes__lte=MAX_MINUTES),
                name="appointment_duration",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "pending",
                        "confirmed",
                        "in_progress",
                        "completed",
                        "cancelled",
                        "no_show",
                    ]
                ),
                name="appointment_status",
            ),
            models.CheckConstraint(
                condition=Q(source__in=["counter", "phone", "online", "whatsapp"]),
                name="appointment_source",
            ),
            models.UniqueConstraint(
                fields=["recurring", "occurrence_date"],
                condition=Q(deleted_at__isnull=True, recurring__isnull=False),
                name="appointment_one_per_occurrence",
            ),
        ]

    def __str__(self) -> str:
        return self.number


class AppointmentService(UUIDModel):
    """A service of an appointment as it was booked: its name, price and length, frozen."""

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("appointment"),
    )
    service = models.ForeignKey(
        "service.Service",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("service"),
    )
    name = models.CharField(_("name"), max_length=200)
    price = models.PositiveBigIntegerField(_("price"))
    duration_minutes = models.PositiveIntegerField(_("duration (min)"))
    position = models.PositiveSmallIntegerField(_("position"), default=0)

    class Meta:
        verbose_name = _("service of an appointment")
        verbose_name_plural = _("services of an appointment")
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["appointment", "position"], name="appointment_line_position"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class History(UUIDModel):
    """One change of an appointment: what happened, when, who did it and, for a move, from what to what."""

    class Action(models.TextChoices):
        CREATED = "created", _("Booked")
        CONFIRMED = "confirmed", _("Confirmed")
        STARTED = "started", _("Service started")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")
        NO_SHOW = "no_show", _("Did not show up")
        RESCHEDULED = "rescheduled", _("Time changed")
        STAFF_CHANGED = "staff_changed", _("Professional changed")
        SERVICE_CHANGED = "service_changed", _("Service changed")
        UNASSIGNED = "unassigned", _("Professional left: to be reassigned")
        CHARGED = "charged", _("Charged")
        UNCHARGED = "uncharged", _("Sale voided")
        DELETED = "deleted", _("Deleted")

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name=_("appointment"),
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    at = models.DateTimeField(_("at"), auto_now_add=True)
    actor = models.CharField(_("by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    by_customer = models.BooleanField(_("requested by the customer"), default=False)
    reason = models.CharField(_("reason"), max_length=500, blank=True)
    old_value = models.JSONField(_("before"), default=dict, blank=True)
    new_value = models.JSONField(_("after"), default=dict, blank=True)

    class Meta:
        verbose_name = _("appointment history line")
        verbose_name_plural = _("appointment history")
        ordering = ["at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    action__in=[
                        "created",
                        "confirmed",
                        "started",
                        "completed",
                        "cancelled",
                        "no_show",
                        "rescheduled",
                        "staff_changed",
                        "service_changed",
                        "unassigned",
                        "charged",
                        "uncharged",
                        "deleted",
                    ]
                ),
                name="appointment_history_action",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.appointment_id} {self.action}"


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
