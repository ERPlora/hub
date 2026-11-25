"""Two active root rules of one slot never apply on the same day: the lock that queues the writes, and the check."""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict

from apps.tax.models import TaxCategory, TaxRule

RULE_OVERLAPS = _(
    "It overlaps another active rule of this country, region and category: two rates cannot apply on the "
    "same day. End that rule the day before this one starts, or deactivate it."
)


def _lock(categories: list[TaxCategory]) -> None:
    """Lock the categories' rows until the end of the command, always in the same order (no deadlock)."""
    list(
        TaxCategory.objects.select_for_update()
        .filter(pk__in=[c.pk for c in categories])
        .order_by("key")
    )


def _overlapping(rule: TaxRule) -> TaxRule | None:
    """Another active root rule of ``rule``'s slot in force on a day ``rule`` is (inclusive ranges)."""
    if rule.parent_id is not None or not rule.is_active:
        return None
    others = TaxRule.objects.filter(
        parent__isnull=True,
        is_active=True,
        country_code=rule.country_code,
        region_code=rule.region_code,
        category_id=rule.category_id,
    ).exclude(pk=rule.pk)
    if rule.valid_to is not None:
        others = others.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=rule.valid_to)
        )
    if rule.valid_from is not None:
        others = others.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=rule.valid_from)
        )
    return others.order_by("id").first()


def _refuse_overlap(rule: TaxRule, field: str | None) -> None:
    if _overlapping(rule) is not None:
        fields = {field: str(RULE_OVERLAPS)} if field else None
        raise Conflict(RULE_OVERLAPS, code="tax.rule_overlaps", fields=fields)
