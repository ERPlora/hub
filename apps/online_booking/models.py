"""Models of the online booking app: the public page's settings and the link of each booking made on it.

A booking is an appointment of Citas (``source = "online"``): status, time, services, professional and the
customer's card live there. This app keeps only what is its own: the page (one row; without it, the factory
values apply) and, for each booking made on the page, the hash of the customer's link and a fingerprint of
the visitor (for the limits), both emptied when her data is erased. Phase 1 has no tenancy: every scope
shares these tables; phase 2 moves them to each hub's database.
"""

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
#: SHA-256 in hex: the link's hash and the visitor's fingerprint.
HASH_LENGTH = 64


class Settings(UUIDModel):
    """The public booking page: one row at most; without it, the factory values (the page off)."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    is_enabled = models.BooleanField(_("public page on"), default=False)
    # Empty = the page's own title and messages, in the visitor's language.
    page_title = models.CharField(_("page title"), max_length=120, blank=True)
    welcome_message = models.TextField(_("welcome message"), blank=True)
    primary_color = models.CharField(
        _("primary colour"), max_length=7, default="#6366f1"
    )
    logo_url = models.CharField(_("logo URL"), max_length=500, blank=True)
    # The mobile is always required: it is how the customer is recognised (Customers); the email is optional
    # unless the business asks for it (the market: Square, Timely, Mangomint).
    require_email = models.BooleanField(_("email required"), default=False)
    # The upcoming online bookings one mobile may hold at once (Cal.com, SimplyBook.me).
    max_upcoming_per_customer = models.PositiveSmallIntegerField(
        _("upcoming bookings per customer"), default=3
    )
    allow_staff_selection = models.BooleanField(
        _("customers choose the professional"), default=True
    )
    allow_notes = models.BooleanField(_("customers may leave a note"), default=True)
    confirmation_message = models.TextField(_("confirmation message"), blank=True)
    cancellation_policy = models.TextField(_("cancellation policy"), blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("online booking settings")
        verbose_name_plural = _("online booking settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="online_booking_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="online_booking_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(
                    max_upcoming_per_customer__gte=1, max_upcoming_per_customer__lte=50
                ),
                name="online_booking_settings_upcoming_range",
            ),
        ]

    def __str__(self) -> str:
        return str(_("Online booking settings"))


class Booking(UUIDModel):
    """An appointment booked on the public page: the hash of the customer's link and the visitor's fingerprint."""

    appointment = models.OneToOneField(
        "appointment.Appointment",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("appointment"),
    )
    # Empty (NULL) = revoked: the link no longer opens anything.
    token_hash = models.CharField(
        _("link hash"), max_length=HASH_LENGTH, null=True, blank=True, unique=True
    )
    # Who booked, as a fingerprint of the device (never the address itself); emptied on erasure.
    requester = models.CharField(_("visitor"), max_length=HASH_LENGTH, blank=True)
    created_at = models.DateTimeField(_("booked at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("online booking")
        verbose_name_plural = _("online bookings")
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(
                fields=["requester", "created_at"], name="online_booking_requester_idx"
            )
        ]

    def __str__(self) -> str:
        return self.appointment.number
