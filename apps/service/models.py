"""Models of the service app: the settings, the service catalog and its categories, who performs each
service, and the vouchers (the catalog's packages, the ones sold, their adjustments and sessions).

Money is in cents (integers, never negative); a percentage discount in basis points (1050 = 10.50 %).
A service is archived and a category or a package deleted logically: what points at them keeps
pointing. A voucher sold (``Grant``) freezes its terms; its balance is computed when read, from its
sessions (``Redemption``) and its adjustments (``GrantAdjustment``), never stored. Phase 1 has no
tenancy: every scope shares these tables; phase 2 moves them to each hub's database.
"""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
#: The most a voucher's sessions move in one adjustment, and the most days it is extended.
MAX_ADJUST_USES = 100
MAX_ADJUST_DAYS = 366


class ServiceSettings(UUIDModel):
    """The business's service settings: one row at most; without it, the factory values apply."""

    singleton = models.BooleanField(_("single row"), default=True, editable=False)
    # What a new service takes when it does not say (form, assistant, API, bulk create).
    default_duration = models.PositiveIntegerField(
        _("default duration (min)"), default=60
    )
    default_buffer_time = models.PositiveIntegerField(
        _("default buffer time (min)"), default=0
    )
    default_tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("default tax category"),
    )
    # For the public booking page, when it exists.
    show_prices = models.BooleanField(_("show prices"), default=True)
    show_duration = models.BooleanField(_("show duration"), default=True)
    allow_online_booking = models.BooleanField(_("allow online booking"), default=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("service settings")
        verbose_name_plural = _("service settings")
        constraints = [
            models.UniqueConstraint(
                fields=["singleton"], name="service_settings_single_row"
            ),
            models.CheckConstraint(
                condition=Q(singleton=True), name="service_settings_singleton"
            ),
            models.CheckConstraint(
                condition=Q(default_duration__gte=1), name="service_settings_duration"
            ),
        ]

    def __str__(self) -> str:
        return str(self._meta.verbose_name)


CATEGORY_CYCLE = _(
    "A category cannot hang from itself or from one of its subcategories."
)
CATEGORY_LOOP = _(
    "These categories hang from each other in a loop: leave one of them without a parent and try again."
)


def parent_problem(
    category_id: UUID, parent_id: UUID | None, parent_of: Mapping[UUID, UUID | None]
) -> Literal["cycle", "loop"] | None:
    """Why ``category_id`` cannot hang from ``parent_id``, walking up ``parent_of`` (id → parent id).

    ``"cycle"`` when the parent is the category itself or one of its descendants; ``"loop"`` when the
    ancestors already loop (a raw write left it so): the walk stops at the first repeated category.
    """
    seen: set[UUID] = set()
    current = parent_id
    while current is not None:
        if current == category_id:
            return "cycle"
        if current in seen:
            return "loop"
        seen.add(current)
        current = parent_of.get(current)
    return None


class Category(UUIDModel):
    """A group of services («Hair», «Colour»), optionally inside another one; deleted logically."""

    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("parent category"),
    )
    icon = models.CharField(_("icon"), max_length=80, blank=True)
    color = models.CharField(_("colour"), max_length=7, blank=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
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
        verbose_name = _("service category")
        verbose_name_plural = _("service categories")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            # A deleted category frees its name for a new one.
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(is_deleted=False),
                name="service_category_live_name_unique",
            ),
            models.CheckConstraint(
                condition=~Q(parent=F("id")), name="service_category_not_own_parent"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Service(UUIDModel):
    """A service of the catalog; archived (``is_active`` off), never deleted."""

    class PricingType(models.TextChoices):
        FIXED = "fixed", _("Fixed price")
        HOURLY = "hourly", _("Hourly")
        FROM = "from", _("From")
        VARIABLE = "variable", _("Variable")
        FREE = "free", _("Free")

    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    short_description = models.TextField(_("short description"), blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services",
        verbose_name=_("category"),
    )
    pricing_type = models.CharField(
        _("pricing"),
        max_length=10,
        choices=PricingType.choices,
        default=PricingType.FIXED,
    )
    price = models.PositiveBigIntegerField(_("price"), default=0)
    min_price = models.PositiveBigIntegerField(
        _("minimum price"), null=True, blank=True
    )
    max_price = models.PositiveBigIntegerField(
        _("maximum price"), null=True, blank=True
    )
    cost = models.PositiveBigIntegerField(_("cost"), default=0)
    duration_minutes = models.PositiveIntegerField(_("duration (min)"), default=60)
    buffer_before = models.PositiveIntegerField(_("buffer before (min)"), default=0)
    buffer_after = models.PositiveIntegerField(_("buffer after (min)"), default=0)
    max_capacity = models.PositiveIntegerField(_("capacity"), default=1)
    is_bookable = models.BooleanField(_("bookable"), default=True)
    requires_confirmation = models.BooleanField(
        _("requires confirmation"), default=False
    )
    allow_online_booking = models.BooleanField(_("online booking"), default=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_featured = models.BooleanField(_("featured"), default=False)
    sku = models.CharField(_("SKU"), max_length=64, blank=True)
    barcode = models.CharField(_("barcode"), max_length=64, blank=True)
    notes = models.TextField(_("notes"), blank=True)
    # Without a live one it cannot be charged (it needs tax setup); tax.TaxCategory is never deleted.
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("tax category"),
    )
    is_active = models.BooleanField(_("offered"), default=True)
    archived_at = models.DateTimeField(_("archived at"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["name", "id"], name="service_service_name_idx"),
            models.Index(
                fields=["is_active", "name"], name="service_service_offered_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    pricing_type__in=["fixed", "hourly", "from", "variable", "free"]
                ),
                name="service_service_pricing_type",
            ),
            models.CheckConstraint(
                condition=Q(min_price__isnull=True)
                | Q(max_price__isnull=True)
                | Q(min_price__lte=F("max_price")),
                name="service_service_price_range",
            ),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1), name="service_service_duration"
            ),
            models.CheckConstraint(
                condition=Q(max_capacity__gte=1), name="service_service_capacity"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Assignment(UUIDModel):
    """A professional of Staff who performs a service, with their own duration and price if any."""

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("service"),
    )
    member = models.ForeignKey(
        "staff.Member",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("professional"),
    )
    # Empty = the catalog's.
    custom_duration = models.PositiveIntegerField(
        _("own duration (min)"), null=True, blank=True
    )
    custom_price = models.PositiveBigIntegerField(_("own price"), null=True, blank=True)
    # The professional's main service: one per professional; it only orders the lists.
    is_primary = models.BooleanField(_("main service"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("professional of a service")
        verbose_name_plural = _("professionals of the services")
        ordering = ["-is_primary", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "member"], name="service_assignment_unique"
            ),
            models.UniqueConstraint(
                fields=["member"],
                condition=Q(is_primary=True),
                name="service_assignment_one_primary",
            ),
            models.CheckConstraint(
                condition=Q(custom_duration__isnull=True) | Q(custom_duration__gte=1),
                name="service_assignment_duration",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.member_id} → {self.service_id}"


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
        _("voided by"), max_length=ACTOR_MAX_LENGTH, blank=True
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
