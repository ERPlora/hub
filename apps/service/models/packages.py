"""The vouchers of the catalog (packages) and their lines; a package is deleted logically."""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.service.models.catalog import Service
from apps.service.models.settings import ACTOR_MAX_LENGTH


class Package(UUIDModel):
    """A voucher of the catalog: sessions of some services, sold once and spent over several visits."""

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FIXED = "fixed", _("Fixed amount")

    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    discount_type = models.CharField(
        _("discount type"),
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    # Basis points: 1050 = 10.50 %.
    discount_percent_bp = models.PositiveIntegerField(
        _("discount (basis points)"), default=0
    )
    discount_amount = models.PositiveBigIntegerField(_("discount (amount)"), default=0)
    # Empty = the sum of its lines minus the discount.
    fixed_price = models.PositiveBigIntegerField(
        _("closed price"), null=True, blank=True
    )
    # Days redeemable from the purchase; empty = never expires.
    validity_days = models.PositiveIntegerField(
        _("validity (days)"), null=True, blank=True
    )
    # Sessions the voucher grants in all; empty = unlimited.
    max_uses = models.PositiveIntegerField(_("uses"), null=True, blank=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    is_featured = models.BooleanField(_("featured"), default=False)
    is_deleted = models.BooleanField(_("deleted"), default=False)
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
        verbose_name = _("package")
        verbose_name_plural = _("packages")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_deleted=False),
                name="service_package_live_name_unique",
            ),
            models.CheckConstraint(
                condition=Q(discount_type__in=["percentage", "fixed"])
                & Q(discount_percent_bp__lte=10000),
                name="service_package_discount",
            ),
            models.CheckConstraint(
                condition=(Q(validity_days__isnull=True) | Q(validity_days__gte=1))
                & (Q(max_uses__isnull=True) | Q(max_uses__gte=1)),
                name="service_package_voucher",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PackageItem(UUIDModel):
    """A line of a voucher: a service and how many sessions of it (they do not limit anything yet)."""

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("package"),
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="+", verbose_name=_("service")
    )
    sessions = models.PositiveIntegerField(_("sessions"), default=1)
    sort_order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("package line")
        verbose_name_plural = _("package lines")
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["package", "service"], name="service_package_item_unique"
            ),
            models.CheckConstraint(
                condition=Q(sessions__gte=1), name="service_package_item_sessions"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package_id} · {self.service_id} × {self.sessions}"
