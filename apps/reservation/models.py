"""The book of reservations: its rules (one row), the slots it books, the blocked dates, the reservations
and the waitlist.

A reservation keeps its day and time on the business's wall clock («Thursday at 21:00»), as they are said
on the phone; Tables turns them into the hold's instants. Its table is a table of Tables and its guest a
card of Customers (``requires``); the guest's name, phone and email are copies, emptied when the
customer's data is erased. Slots, blocked dates, reservations and waitlist entries are deleted softly.
"""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

#: Who saved a row, as a person reads it (a user's name, the system's label).
ACTOR_MAX_LENGTH = 150
#: The most a reservation lasts, and the most guests it brings.
MAX_MINUTES = 24 * 60
MAX_GUESTS = 999


class Audited(UUIDModel):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        abstract = True


class Settings(UUIDModel):
    """The book's rules (one row): the factory ones until somebody saves them."""

    singleton = models.BooleanField(
        _("single row"), default=True, unique=True, editable=False
    )
    min_party_size = models.PositiveSmallIntegerField(_("minimum guests"), default=1)
    max_party_size = models.PositiveSmallIntegerField(_("maximum guests"), default=20)
    # Only for the bookings the guest makes herself (online, WhatsApp): the staff book from now on.
    min_advance_hours = models.PositiveSmallIntegerField(
        _("minimum notice (hours)"), default=1
    )
    max_advance_days = models.PositiveSmallIntegerField(
        _("maximum days ahead"), default=30
    )
    default_duration_minutes = models.PositiveSmallIntegerField(
        _("default duration (minutes)"), default=120
    )
    auto_confirm = models.BooleanField(
        _("confirm new reservations automatically"), default=False
    )
    require_phone = models.BooleanField(_("phone required"), default=True)
    require_email = models.BooleanField(_("email required"), default=False)
    no_show_window_minutes = models.PositiveSmallIntegerField(
        _("release an unconfirmed reservation after (minutes)"), default=15
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("reservation settings")
        verbose_name_plural = _("reservation settings")
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    min_party_size__gte=1, max_party_size__gte=F("min_party_size")
                ),
                name="reservation_settings_party",
            ),
            models.CheckConstraint(
                condition=Q(
                    default_duration_minutes__gte=1,
                    default_duration_minutes__lte=MAX_MINUTES,
                ),
                name="reservation_settings_duration",
            ),
        ]

    def __str__(self) -> str:
        return str(_("Reservation settings"))


class TimeSlot(Audited):
    """A window of a weekday the book takes reservations in, with how many fit (reservations, covers)."""

    day_of_week = models.PositiveSmallIntegerField(_("day of the week"))
    start_time = models.TimeField(_("from"))
    end_time = models.TimeField(_("to"))
    max_reservations = models.PositiveSmallIntegerField(
        _("maximum reservations"), default=10
    )
    # Empty = the slot counts reservations only (the old module's rule).
    max_covers = models.PositiveSmallIntegerField(
        _("maximum guests"), null=True, blank=True
    )
    is_deleted = models.BooleanField(
        pgettext_lazy("reservation", "deleted"), default=False
    )
    deleted_at = models.DateTimeField(
        pgettext_lazy("reservation", "deleted at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("time slot")
        verbose_name_plural = _("time slots")
        ordering = ["day_of_week", "start_time", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(day_of_week__gte=0, day_of_week__lte=6),
                name="reservation_slot_weekday",
            ),
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="reservation_slot_ends_after_start",
            ),
            models.CheckConstraint(
                condition=Q(max_reservations__gte=1),
                name="reservation_slot_max_reservations",
            ),
            models.CheckConstraint(
                condition=Q(max_covers__isnull=True) | Q(max_covers__gte=1),
                name="reservation_slot_max_covers",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.day_of_week} {self.start_time:%H:%M}–{self.end_time:%H:%M}"


class BlockedDate(Audited):
    """A day (or some hours of it) the book takes no reservations: a holiday, a closure, a private event."""

    date = models.DateField(_("date"))
    reason = models.CharField(_("reason"), max_length=200, blank=True)
    is_full_day = models.BooleanField(_("whole day"), default=True)
    blocked_from = models.TimeField(_("from"), null=True, blank=True)
    blocked_until = models.TimeField(_("until"), null=True, blank=True)
    is_deleted = models.BooleanField(
        pgettext_lazy("reservation", "deleted"), default=False
    )
    deleted_at = models.DateTimeField(
        pgettext_lazy("reservation", "deleted at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("blocked date")
        verbose_name_plural = _("blocked dates")
        ordering = ["date", "blocked_from", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_full_day=True)
                | Q(
                    blocked_from__isnull=False,
                    blocked_until__isnull=False,
                    blocked_until__gt=F("blocked_from"),
                ),
                name="reservation_blocked_window",
            ),
            models.UniqueConstraint(
                fields=["date", "blocked_from"],
                condition=Q(is_deleted=False),
                nulls_distinct=False,
                name="reservation_blocked_once",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.reason}".strip()


class Reservation(Audited):
    """A table booked for a party at a day and time of the business, from pending to completed."""

    # Short labels carry a context: Django merges the apps' catalogues, and another app may translate
    # the same word otherwise («Pending» → «Pendiente» / «Pendiente de pago»).
    class Status(models.TextChoices):
        PENDING = "pending", pgettext_lazy("reservation status", "Pending")
        CONFIRMED = "confirmed", pgettext_lazy("reservation status", "Confirmed")
        SEATED = "seated", pgettext_lazy("reservation status", "Seated")
        COMPLETED = "completed", pgettext_lazy("reservation status", "Completed")
        CANCELLED = "cancelled", pgettext_lazy("reservation status", "Cancelled")
        NO_SHOW = "no_show", pgettext_lazy("reservation status", "No-show")

    class Source(models.TextChoices):
        PHONE = "phone", pgettext_lazy("reservation source", "Phone")
        IN_PERSON = "in_person", pgettext_lazy("reservation source", "In person")
        WAITLIST = "waitlist", pgettext_lazy("reservation source", "Waitlist")
        WHATSAPP = "whatsapp", pgettext_lazy("reservation source", "WhatsApp")
        ONLINE = "online", pgettext_lazy("reservation source", "Online")

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("customer"),
    )
    # Copies of the card at booking time (emptied when the customer's data is erased).
    guest_name = models.CharField(_("guest's name"), max_length=200, blank=True)
    guest_phone = models.CharField(_("guest's phone"), max_length=60, blank=True)
    guest_email = models.CharField(_("guest's email"), max_length=254, blank=True)
    date = models.DateField(_("date"))
    time = models.TimeField(_("time"))
    party_size = models.PositiveSmallIntegerField(_("guests"), default=2)
    duration_minutes = models.PositiveSmallIntegerField(
        _("duration (minutes)"), default=120
    )
    table = models.ForeignKey(
        "table.Table",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("table"),
    )
    status = models.CharField(
        _("status"), max_length=12, choices=Status.choices, default=Status.PENDING
    )
    source = models.CharField(
        _("booked through"), max_length=12, choices=Source.choices, default=Source.PHONE
    )
    # Visible to the guest; the internal one may hold health data (an allergy, a wheelchair).
    notes = models.TextField(_("notes"), blank=True)
    internal_notes = models.TextField(_("internal notes"), blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    seated_at = models.DateTimeField(_("seated at"), null=True, blank=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    no_show_at = models.DateTimeField(_("marked no-show at"), null=True, blank=True)
    cancellation_reason = models.CharField(
        _("cancellation reason"), max_length=500, blank=True
    )
    # The check of Tables seating it opened (an opaque id: Tables' own record).
    table_session_id = models.UUIDField(_("table check"), null=True, blank=True)
    is_deleted = models.BooleanField(
        pgettext_lazy("reservation", "deleted"), default=False
    )
    deleted_at = models.DateTimeField(
        pgettext_lazy("reservation", "deleted at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("reservation")
        verbose_name_plural = _("reservations")
        ordering = ["date", "time", "id"]
        indexes = [
            models.Index(fields=["date", "time"], name="reservation_day_idx"),
            models.Index(fields=["table", "date"], name="reservation_table_day_idx"),
            models.Index(fields=["customer", "date"], name="reservation_customer_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "pending",
                        "confirmed",
                        "seated",
                        "completed",
                        "cancelled",
                        "no_show",
                    ]
                ),
                name="reservation_status",
            ),
            models.CheckConstraint(
                condition=Q(
                    source__in=["phone", "in_person", "waitlist", "whatsapp", "online"]
                ),
                name="reservation_source",
            ),
            models.CheckConstraint(
                condition=Q(party_size__gte=1, party_size__lte=MAX_GUESTS),
                name="reservation_party",
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1, duration_minutes__lte=MAX_MINUTES),
                name="reservation_duration",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guest_name} · {self.date} {self.time:%H:%M}"


class WaitlistEntry(Audited):
    """Somebody waiting for a table on a day, around a time; converted, it points at its reservation."""

    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("customer"),
    )
    guest_name = models.CharField(_("guest's name"), max_length=200, blank=True)
    guest_phone = models.CharField(_("guest's phone"), max_length=60, blank=True)
    guest_email = models.CharField(_("guest's email"), max_length=254, blank=True)
    date = models.DateField(_("date"))
    preferred_time = models.TimeField(_("preferred time"))
    party_size = models.PositiveSmallIntegerField(_("guests"), default=2)
    notes = models.TextField(_("notes"), blank=True)
    is_contacted = models.BooleanField(_("contacted"), default=False)
    contacted_at = models.DateTimeField(_("contacted at"), null=True, blank=True)
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="waitlist_entry",
        verbose_name=_("reservation"),
    )
    is_deleted = models.BooleanField(
        pgettext_lazy("reservation", "deleted"), default=False
    )
    deleted_at = models.DateTimeField(
        pgettext_lazy("reservation", "deleted at"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("waitlist entry")
        verbose_name_plural = _("waitlist")
        # The order people were written down in, stable: day, preferred time, arrival, id.
        ordering = ["date", "preferred_time", "created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(party_size__gte=1, party_size__lte=MAX_GUESTS),
                name="reservation_waitlist_party",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.guest_name} · {self.date} {self.preferred_time:%H:%M}"
