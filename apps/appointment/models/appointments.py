"""The appointments: each with the services it was booked with, frozen, and the history of its changes."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.appointment.models.audit import Audited
from apps.appointment.models.series import Recurring
from apps.appointment.models.settings import ACTOR_MAX_LENGTH, MAX_MINUTES


class Appointment(Audited):
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
    # Own context, as Audited's (hub#633).
    updated_by = models.CharField(
        pgettext_lazy("appointment", "updated by"),
        max_length=ACTOR_MAX_LENGTH,
        blank=True,
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
        RESTORED = "restored", pgettext_lazy("appointment history", "Restored")

    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name=_("appointment"),
    )
    action = models.CharField(_("action"), max_length=16, choices=Action.choices)
    at = models.DateTimeField(_("at"), auto_now_add=True)
    # Own context: the history says «quién» did each change, not Clientes' «por» of the same English (hub#633).
    actor = models.CharField(
        pgettext_lazy("appointment", "by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
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
                        "restored",
                    ]
                ),
                name="appointment_history_action",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.appointment_id} {self.action}"
