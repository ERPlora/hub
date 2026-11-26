"""The vouchers sold, their adjustments and their sessions.

A voucher sold (``Grant``) freezes its terms; its balance is computed when read, from its sessions
(``Redemption``) and its adjustments (``GrantAdjustment``), never stored.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.models import UUIDModel

from apps.service.models.catalog import Service
from apps.service.models.packages import Package
from apps.service.models.settings import ACTOR_MAX_LENGTH

#: The most a voucher's sessions move in one adjustment, and the most days it is extended.
MAX_ADJUST_USES = 100
MAX_ADJUST_DAYS = 366


class Grant(UUIDModel):
    """A voucher sold to a customer: who owns it, when, for how much, and its terms frozen."""

    class Source(models.TextChoices):
        MANUAL = "manual", _("Granted by hand")
        SALE = "sale", _("Sold at the till")

    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="grants",
        verbose_name=_("package"),
    )
    customer = models.ForeignKey(
        "customer.Customer",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("customer"),
    )
    granted_at = models.DateTimeField(_("bought at"), default=timezone.now)
    source = models.CharField(
        _("source"), max_length=8, choices=Source.choices, default=Source.MANUAL
    )
    # The sale that paid it, when there is one: an opaque id of the Sales app (not a requirement).
    sale_id = models.UUIDField(_("sale"), null=True, blank=True)
    # The line of that sale that charged it (opaque too), if it said so. A paid voucher without it does not count as its
    # sessions are done: its money may already count for who sold it, on a line nobody named (SERVICE-F24).
    sale_line_id = models.UUIDField(_("sale line"), null=True, blank=True)
    amount = models.PositiveBigIntegerField(_("amount paid"), default=0)
    net_amount = models.PositiveBigIntegerField(_("net amount"), default=0)
    tax_amount = models.PositiveBigIntegerField(_("tax amount"), default=0)
    # The package's terms when it was sold: changing the package later does not touch them.
    max_uses = models.PositiveIntegerField(_("uses"), null=True, blank=True)
    validity_days = models.PositiveIntegerField(
        _("validity (days)"), null=True, blank=True
    )
    note = models.CharField(_("note"), max_length=500, blank=True)
    voided_at = models.DateTimeField(_("voided at"), null=True, blank=True)
    voided_by = models.CharField(
        # Its own context: the voucher sold is masculine («anulado por»), a sale of Sales is not.
        pgettext_lazy("service", "voided by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    void_reason = models.CharField(_("void reason"), max_length=500, blank=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("voucher sold")
        verbose_name_plural = _("vouchers sold")
        ordering = ["-granted_at", "-id"]
        indexes = [
            models.Index(
                fields=["package", "-granted_at"], name="service_grant_package_idx"
            ),
            models.Index(
                fields=["customer", "-granted_at"], name="service_grant_customer_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(source__in=["manual", "sale"]), name="service_grant_source"
            ),
            models.CheckConstraint(
                condition=(Q(max_uses__isnull=True) | Q(max_uses__gte=1))
                & (Q(validity_days__isnull=True) | Q(validity_days__gte=1)),
                name="service_grant_terms",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_id} → {self.customer_id}"


class GrantAdjustment(UUIDModel):
    """A courtesy or a correction on a voucher sold: sessions added or taken, days added; never edited."""

    grant = models.ForeignKey(
        Grant,
        on_delete=models.PROTECT,
        related_name="adjustments",
        verbose_name=_("voucher sold"),
    )
    uses_delta = models.SmallIntegerField(_("sessions"), default=0)
    days_delta = models.PositiveSmallIntegerField(_("days"), default=0)
    reason = models.CharField(_("reason"), max_length=500)
    actor = models.CharField(_("by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    created_at = models.DateTimeField(_("date"), default=timezone.now)

    class Meta:
        verbose_name = _("voucher adjustment")
        verbose_name_plural = _("voucher adjustments")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(uses_delta=0) | ~Q(days_delta=0),
                name="service_adjustment_moves_something",
            ),
            models.CheckConstraint(
                condition=Q(uses_delta__gte=-MAX_ADJUST_USES)
                & Q(uses_delta__lte=MAX_ADJUST_USES)
                & Q(days_delta__lte=MAX_ADJUST_DAYS),
                name="service_adjustment_bounds",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.grant_id}: {self.uses_delta:+d} / +{self.days_delta}"


class Redemption(UUIDModel):
    """A session of a voucher sold: held for a line of the till, delivered, released, expired or given back.

    A session spent outside the till is born ``consumed``. One held at the till (``held``) covers one
    line of an open check (``order_line_id``, an opaque id of the Sales app) until ``hold_until``;
    charging the sale delivers it (``consumed``, ``sale_id``, ``settled_at``), undoing it releases it,
    the deadline expires it, and voiding or refunding its sale gives it back (``returned``). Only the
    state and its trail move: nothing else is ever edited.
    """

    class Status(models.TextChoices):
        HELD = "held", _("Held")
        CONSUMED = "consumed", _("Delivered")
        RELEASED = "released", _("Released")
        EXPIRED = "expired", _("Expired")
        RETURNED = "returned", _("Given back")

    #: The states that count against the balance (a hold only until its deadline).
    LIVE = (Status.HELD, Status.CONSUMED)

    grant = models.ForeignKey(
        Grant,
        on_delete=models.PROTECT,
        related_name="redemptions",
        verbose_name=_("voucher sold"),
    )
    # The service performed, when it was said.
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("service"),
    )
    # The professional of Staff who did it, when it was said (SERVICE-F21): a session spent outside the till counts in
    # her production (SALE-F28). One of the till is said on its line, in Sales.
    member = models.ForeignKey(
        "staff.Member",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("professional"),
    )
    # Opaque ids of the Appointments and Sales apps (not requirements).
    appointment_id = models.UUIDField(_("appointment"), null=True, blank=True)
    sale_id = models.UUIDField(_("sale"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=500, blank=True)
    actor = models.CharField(_("by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    redeemed_at = models.DateTimeField(_("date"), default=timezone.now)
    status = models.CharField(
        _("state"), max_length=10, choices=Status.choices, default=Status.CONSUMED
    )
    # The line of an open check of the Sales app the session is held for (opaque id).
    order_line_id = models.UUIDField(_("check line"), null=True, blank=True)
    hold_until = models.DateTimeField(_("held until"), null=True, blank=True)
    settled_at = models.DateTimeField(_("charged at"), null=True, blank=True)
    # When and by whom it stopped counting: released, expired or given back.
    ended_at = models.DateTimeField(_("ended at"), null=True, blank=True)
    ended_by = models.CharField(_("ended by"), max_length=ACTOR_MAX_LENGTH, blank=True)
    # The refund or the voided sale of the Sales app that gave it back (opaque id), and why.
    return_reference = models.UUIDField(_("given back by"), null=True, blank=True)
    return_reason = models.CharField(
        _("reason it came back"), max_length=500, blank=True
    )
    # What it is worth, VAT included, fixed when it is delivered and never moved again (SERVICE-F24). Empty while
    # it is not delivered, and on an unlimited voucher, which has no sessions to divide its price by.
    value = models.PositiveBigIntegerField(_("value"), null=True, blank=True)

    class Meta:
        verbose_name = _("voucher session")
        verbose_name_plural = _("voucher sessions")
        ordering = ["-redeemed_at", "-id"]
        indexes = [
            models.Index(
                fields=["grant", "-redeemed_at"], name="service_redemption_grant_idx"
            ),
            models.Index(
                fields=["status", "hold_until"], name="service_redemption_hold_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["held", "consumed", "released", "expired", "returned"]
                ),
                name="service_redemption_status",
            ),
            models.UniqueConstraint(
                fields=["order_line_id"],
                condition=Q(status__in=["held", "consumed"]),
                name="service_redemption_one_per_line",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.grant_id} @ {self.redeemed_at:%Y-%m-%d}"
