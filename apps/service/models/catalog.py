"""The service catalog: its categories, the services and the professionals of Staff who perform each one.

A service is archived and a category deleted logically: what points at them keeps pointing.
"""

from collections.abc import Mapping
from typing import Literal
from uuid import UUID

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

from apps.service.models.settings import ACTOR_MAX_LENGTH

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
    # Its image (SERVICE-F34, F35; base.images): one of the shared library («catalog:<folder>/<name>») or a photo of its
    # own («file:service/services/<uuid7 hex>.webp» under its hub's prefix); empty: none, the till shows its initials.
    # Never a URL. ``db_default``: a process still on the previous code inserts without it.
    image = models.CharField(_("image"), max_length=200, blank=True, default="", db_default="")
    # The id, in a separate copy of the business, of the service a recovery made this one again for (BASE-F114): a
    # service has no code of its own, so it is how an app whose records hang from the copy's finds this one.
    stands_for = models.UUIDField(_("copy's service it stands for"), null=True, blank=True, editable=False)
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
