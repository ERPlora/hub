"""The one resolution of a rate that sales and invoice share: which root rule applies to a country, a region, a
category and a date, and its components.

Resolution: the candidates are the active root rules of the country and the category in force on the
date; an exact region beats the whole country and a rule of another region is never used; a region with a
tax of its own (IGIC, IPSI) only takes its own rules, never the national VAT; inside a
level the newest ``valid_from`` wins, then the lowest ``id``. The root's active components in force
add their rate over the same base. The qualification and the tax family are always the root's.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.tax.models import TaxCategory, TaxRule
from apps.tax.queries.jurisdiction import DEFAULT_TAX_KIND, _jurisdiction, business_today, own_tax_kind

GENERAL_REGIME = "01"


@dataclass(frozen=True)
class Resolution:
    """The root rule that applies and its components (the root first, then its children by id)."""

    root: TaxRule
    components: list[TaxRule] = field(default_factory=list)

    @property
    def rate_pct(self) -> Decimal:
        return sum((component.rate_pct for component in self.components), Decimal(0))

    @property
    def tax_kind(self) -> str:
        return self.root.tax_type or DEFAULT_TAX_KIND

    @property
    def operation_class(self) -> str:
        return self.root.operation_class

    @property
    def regime_key(self) -> str:
        return self.root.regime_key or GENERAL_REGIME

    @property
    def exempt_reason(self) -> str:
        if self.root.operation_class != TaxRule.OperationClass.EXEMPT:
            return ""
        return self.root.exempt_reason.upper()


def _in_force(rules: QuerySet, on: dt.date) -> QuerySet:
    return rules.filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=on),
        Q(valid_to__isnull=True) | Q(valid_to__gte=on),
    )


def _candidate_roots(
    country_code: str, region_code: str | None, on: dt.date
) -> QuerySet:
    regions = ["", region_code] if region_code else [""]
    return _in_force(
        TaxRule.objects.filter(
            parent__isnull=True,
            is_active=True,
            country_code=country_code,
            region_code__in=regions,
        ),
        on,
    )


def _precedence(rule: TaxRule) -> tuple:
    # Newest start first (an empty start, «since always», is the oldest), then the lowest id.
    start = rule.valid_from.toordinal() if rule.valid_from else 0
    return (-start, rule.id.int)


def pick_root(candidates: Iterable[TaxRule], region_code: str | None) -> TaxRule | None:
    """The root rule among ``candidates`` (one category): the region's, else the whole country's — except in a
    region with a tax of its own (the Canary Islands, Ceuta, Melilla: outside the VAT territory), where only its
    own rule applies. There the national VAT never stands in for a missing IGIC or IPSI rule: no rule, as a
    category without any rule elsewhere."""
    candidates = list(candidates)
    for level in ([region_code] if region_code else []) + [""]:
        matching = [
            rule
            for rule in candidates
            if rule.region_code == level and (level or not own_tax_kind(rule.country_code, region_code))
        ]
        if matching:
            return min(matching, key=_precedence)
    return None


def _components(root: TaxRule, on: dt.date) -> list[TaxRule]:
    children = _in_force(root.components.filter(is_active=True), on).order_by("id")
    return [root, *children]


def resolve_tax(
    *,
    category_key: str,
    country_code: str | None = None,
    region_code: str | None = None,
    on: dt.date | None = None,
) -> Resolution | None:
    """The rule that applies to a line of ``category_key`` on ``on`` (default: the business's today), in
    the business's jurisdiction unless a country is named.

    Country and region are read in any case: sales and invoice call this without the schemas.
    """
    on = on or business_today()
    country_code, region_code = _jurisdiction(country_code, region_code)
    candidates = _candidate_roots(country_code, region_code, on).filter(
        category__key=category_key
    )
    root = pick_root(candidates, region_code)
    if root is None:
        return None
    return Resolution(root=root, components=_components(root, on))


def current_rates(categories: list[TaxCategory], country_code: str, region_code: str | None, on: dt.date) -> dict:
    """``{category id: Resolution | None}`` in two queries: the candidates of every category, then the
    components of the chosen roots."""
    candidates: dict[UUID, list[TaxRule]] = {category.id: [] for category in categories}
    for rule in _candidate_roots(country_code, region_code, on).filter(category__in=categories):
        candidates[rule.category_id].append(rule)
    roots = {category_id: pick_root(rules, region_code) for category_id, rules in candidates.items()}
    children: dict[UUID, list[TaxRule]] = {}
    chosen = [root.id for root in roots.values() if root is not None]
    for child in _in_force(TaxRule.objects.filter(parent__in=chosen, is_active=True), on).order_by("id"):
        children.setdefault(child.parent_id, []).append(child)
    return {
        category_id: Resolution(root=root, components=[root, *children.get(root.id, [])]) if root else None
        for category_id, root in roots.items()
    }
