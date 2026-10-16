"""Models of the modifier app: groups of choices, their options and the links to what is sold.

A group says how many options are chosen (``min_choices`` ≥ 1 IS «required»: there is no flag, Clover's
rule) and whether one can be repeated; an option carries its supplement in cents (negative = a
discount) and, only when it taxes differently from the dish, a tax category of its own. A link hangs a
group from exactly one product or one category of Inventory. Phase 1 has no tenancy: every scope shares
these tables; phase 2 moves them to each hub's database.

Deleting is deleting: a group takes its options and links with it (``CASCADE``); Sales keeps its own
frozen copy of what was ordered. Every uniqueness and every rule of a group is held by Postgres too.
"""

from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.models import UUIDModel

ACTOR_MAX_LENGTH = 128
NAME_MAX_LENGTH = 255
#: The most options a group asks for, and the most options a group holds.
MAX_CHOICES = 50
MAX_OPTIONS = 100
#: 999,999.99 € either way: far beyond any supplement, inside a bigint.
MAX_DELTA = 99_999_999


class ModifierGroup(UUIDModel):
    """A reusable group of choices («Sauces», «Doneness»), shared by every product or category it hangs from."""

    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    # The kitchen ticket's name, other than the commercial one (Toast's rule); empty = the name.
    kitchen_name = models.CharField(
        _("kitchen name"), max_length=NAME_MAX_LENGTH, blank=True
    )
    # 1 or more IS required; 0 = optional.
    min_choices = models.PositiveSmallIntegerField(_("minimum choices"), default=0)
    # 0 = no ceiling; otherwise never below the minimum.
    max_choices = models.PositiveSmallIntegerField(_("maximum choices"), default=0)
    # The same option may be chosen more than once («double cheese»).
    allow_repeat = models.BooleanField(_("allow repeat"), default=False)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("modifier group")
        verbose_name_plural = _("modifier groups")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="modifier_group_name_unique"),
            models.CheckConstraint(
                condition=Q(min_choices__lte=MAX_CHOICES)
                & Q(max_choices__lte=MAX_CHOICES),
                name="modifier_group_choices_in_range",
            ),
            models.CheckConstraint(
                condition=Q(max_choices=0) | Q(max_choices__gte=F("min_choices")),
                name="modifier_group_max_not_below_min",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ModifierOption(UUIDModel):
    """One choice of a group («Cheese», «Rare») with its supplement; never stock nor cost of its own."""

    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=_("group"),
    )
    name = models.CharField(_("name"), max_length=NAME_MAX_LENGTH)
    kitchen_name = models.CharField(
        _("kitchen name"), max_length=NAME_MAX_LENGTH, blank=True
    )
    # Cents; may be negative (a discount) or zero (free).
    price_delta = models.BigIntegerField(_("supplement"), default=0)
    # None = the sale line's tax category. With one, it applies to this supplement only, which is
    # billed on a line of its own; tax.TaxCategory is a ``requires`` and is never deleted.
    tax_category = models.ForeignKey(
        "tax.TaxCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("tax category"),
    )
    # Comes chosen when the till opens the group's sheet.
    is_default = models.BooleanField(_("chosen by default"), default=False)
    sort_order = models.PositiveIntegerField(_("order"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )
    updated_by = models.CharField(
        _("updated by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("option")
        verbose_name_plural = _("options")
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                F("group"), Lower("name"), name="modifier_option_name_unique_in_group"
            ),
            models.CheckConstraint(
                condition=Q(price_delta__gte=-MAX_DELTA)
                & Q(price_delta__lte=MAX_DELTA),
                name="modifier_option_delta_in_range",
            ),
            # Its own tax category bills it on a line of its own, which cannot be worth zero or less.
            models.CheckConstraint(
                condition=Q(tax_category__isnull=True) | Q(price_delta__gt=0),
                name="modifier_option_own_line_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ModifierLink(UUIDModel):
    """A group hung from exactly one product or one category of Inventory (its ``requires``)."""

    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name="links",
        verbose_name=_("group"),
    )
    product = models.ForeignKey(
        "inventory.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("product"),
    )
    category = models.ForeignKey(
        "inventory.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("category"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = models.CharField(
        _("created by"), max_length=ACTOR_MAX_LENGTH, blank=True
    )

    class Meta:
        verbose_name = _("link")
        verbose_name_plural = _("links")
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(product__isnull=False) & Q(category__isnull=True))
                | (Q(product__isnull=True) & Q(category__isnull=False)),
                name="modifier_link_one_target",
            ),
            models.UniqueConstraint(
                fields=["group", "product"],
                condition=Q(product__isnull=False),
                name="modifier_link_product_unique",
            ),
            models.UniqueConstraint(
                fields=["group", "category"],
                condition=Q(category__isnull=False),
                name="modifier_link_category_unique",
            ),
        ]

    @property
    def target_kind(self) -> str:
        return "product" if self.product_id else "category"

    def __str__(self) -> str:
        return f"{self.group_id} → {self.target_kind} {self.product_id or self.category_id}"
