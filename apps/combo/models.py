"""Models of the combo app: menus, their courses and the choices of each course.

Money is in cents. A menu's ``price`` is the closed price (never negative); a choice's
``price_delta`` is the supplement it adds to that price (it may be negative, a cheaper substitution).
``supply_kind`` decides how the menu is billed (WORKBOOK COMBO-F09): ``service`` = eaten in, one line
at the menu's own tax category (art. 91.Uno.2.2 LIVA); ``goods`` = sold to take away, split per
component when they do not share a tax category (art. 79.Dos LIVA).

A choice is a product of Inventory (``requires``) by foreign key; the tax category is Taxes' (never
deleted). Deleting is physical and cascades: a sale keeps its own copy of the menu. Phase 1 has no
tenancy: every scope shares these tables; phase 2 moves them to each hub's database.
"""

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

#: The most choices a course asks for, at either end (the old module's schema).
MAX_PICKS = 50
NAME_MAX_LENGTH = 255
ACTOR_MAX_LENGTH = 128


class Combo(UUIDModel):
    """A compound article sold at a closed price: the menu of the day, a sandwich with a drink."""

    class SupplyKind(models.TextChoices):
        SERVICE = "service", _("Eaten in")
        GOODS = "goods", _("Take away")

    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    # Empty: the kitchen ticket uses the name.
    kitchen_name = models.CharField(
        _("kitchen name"), max_length=NAME_MAX_LENGTH, blank=True
    )
    price = models.PositiveBigIntegerField(_("closed price"), default=0)
    supply_kind = models.CharField(
        _("how it is sold"),
        max_length=8,
        choices=SupplyKind.choices,
        default=SupplyKind.SERVICE,
    )
    # The rate of the single line of a menu eaten in; tax.TaxCategory is never deleted.
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("tax category"),
    )
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("on sale"), default=True)
    # Its image (COMBO-F14; round 2026-10-30, base.images): one of the shared library («catalog:<folder>/<name>») or a
    # photo of its own («file:combo/combos/<uuid7 hex>.webp» under its hub's prefix); empty: none, the till shows its
    # initials. Never a URL. ``db_default``: a process still on the previous code inserts menus without it.
    image = models.CharField(_("image"), max_length=200, blank=True, default="", db_default="")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("menu")
        verbose_name_plural = _("menus")
        ordering = ["sort_order", "name", "id"]
        indexes = [
            models.Index(
                fields=["sort_order", "name", "id"], name="combo_combo_order_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(supply_kind__in=["service", "goods"]),
                name="combo_combo_supply_kind_valid",
            ),
            # A menu eaten in is billed in one line at its own rate: without one it cannot be billed.
            models.CheckConstraint(
                condition=~Q(supply_kind="service") | Q(tax_category__isnull=False),
                name="combo_combo_eaten_in_has_a_rate",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ChoiceGroup(UUIDModel):
    """A course of one menu («Starters», «Drink»): how many choices it asks for, in its order."""

    combo = models.ForeignKey(
        Combo, on_delete=models.CASCADE, related_name="groups", verbose_name=_("menu")
    )
    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    # 1 or more IS the obligation: there is no separate flag.
    min_choices = models.PositiveSmallIntegerField(_("minimum picks"), default=1)
    # 0 = no ceiling.
    max_choices = models.PositiveSmallIntegerField(_("maximum picks"), default=1)
    allow_repeat = models.BooleanField(_("may repeat"), default=False)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("course")
        verbose_name_plural = _("courses")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                "combo", Lower("name"), name="combo_group_name_unique"
            ),
            models.CheckConstraint(
                condition=Q(max_choices=0)
                | Q(max_choices__gte=models.F("min_choices")),
                name="combo_group_ceiling_not_below_floor",
            ),
            models.CheckConstraint(
                condition=Q(min_choices__lte=MAX_PICKS) & Q(max_choices__lte=MAX_PICKS),
                name="combo_group_picks_bounded",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ChoiceOption(UUIDModel):
    """A product a course offers, with the supplement it adds to the closed price."""

    group = models.ForeignKey(
        ChoiceGroup,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("course"),
    )
    # Inventory deletes logically; a raw delete of the product takes its choices too.
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        related_name="+",
        verbose_name=_("product"),
    )
    price_delta = models.BigIntegerField(_("supplement"), default=0)
    # Sold out today: kept in the course, not offered.
    is_available = models.BooleanField(_("available"), default=True)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("choice")
        verbose_name_plural = _("choices")
        ordering = ["sort_order", "id"]
        constraints = [
            # The same product twice in one course is a data error; picking it twice is `allow_repeat`.
            models.UniqueConstraint(
                fields=["group", "product"], name="combo_option_product_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.group} · {self.product_id}"
