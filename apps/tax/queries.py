"""Read operations of the tax app (``READ ONLY``), and the one resolution of a rate.

``resolve_tax`` and ``calculate_tax`` are not operations: they are the single implementation of which
rule applies and of the money arithmetic. ``tax.rate.calculate`` wraps them, and sales and invoice
(which require tax) call them inside their own operation, so what is charged, what is declared and
what the assistant says can never drift apart.

Resolution: the candidates are the active root rules of the country and the category in force on the
date; an exact region beats the whole country and a rule of another region is never used; a region with a
tax of its own (IGIC, IPSI) only takes its own rules, never the national VAT; inside a
level the newest ``valid_from`` wins, then the lowest ``id``. The root's active components in force
add their rate over the same base. The qualification and the tax family are always the root's.
"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.conf import settings
from django.db.models import Case, CharField, F, Q, QuerySet, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation

from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxAlias, TaxCategory, TaxRule, TaxSettings
from apps.tax.schemas import (
    DEFAULT_COUNTRY,
    REGION_OF_ANOTHER_COUNTRY,
    REGION_TAX_KINDS,
    TAX_REGIONS,
    AliasListIn,
    AliasPage,
    AliasResolveIn,
    AliasResolveOut,
    CalculateIn,
    CalculationOut,
    CategoryGetIn,
    CategoryListIn,
    CategoryOut,
    CategoryPage,
    RuleCountriesIn,
    RuleCountriesOut,
    RuleListIn,
    RulePage,
    RuleParentIn,
    RuleStatusIn,
    RuleStatusOut,
    SettingsGetIn,
    TaxSettingsOut,
    normalize_text,
)

CATEGORY_NOT_FOUND = _("This tax category does not exist.")
RULE_NOT_FOUND = _("This tax rule no longer exists.")
NO_RATE = _("No tax rule applies to this category in this country.")

GENERAL_REGIME = "01"
DEFAULT_TAX_KIND = TaxRule.TaxType.VAT
_CENT = Decimal(1)
_HUNDRED = Decimal(100)


# ── Money: whole cents, exact decimals, half up ───────────────────────────────────────────────


def round_half_up(value: Decimal) -> int:
    """To the cent, a half away from zero (52.5 → 53, -52.5 → -53)."""
    return int(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def split_amount(
    amount: int, rates: list[Decimal], *, tax_included: bool
) -> tuple[int, int, list[int]]:
    """``(base, tax, quota of each rate)`` of ``amount`` cents, one rounding per magnitude.

    Without the tax, each quota is base × rate. With it, the base is amount ÷ (1 + combined rate) and
    the tax is what remains, so the amount charged never moves a cent; the last component WITH a rate
    absorbs the rounding so that the quotas add up to the tax exactly (a component at 0 % never
    carries a quota; if every rate is 0, there is no tax to adjust).
    """
    if not tax_included:
        quotas = [round_half_up(amount * rate / _HUNDRED) for rate in rates]
        return amount, sum(quotas), quotas
    combined = sum(rates, Decimal(0))
    base = round_half_up(amount * _HUNDRED / (_HUNDRED + combined))
    tax = amount - base
    quotas = [round_half_up(base * rate / _HUNDRED) for rate in rates]
    taxed = [index for index, rate in enumerate(rates) if rate > 0]
    if taxed:
        last = taxed[-1]
        quotas[last] = tax - (sum(quotas) - quotas[last])
    return base, tax, quotas


# ── Resolution ────────────────────────────────────────────────────────────────────────────────


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


def business_today() -> dt.date:
    """The business's today (the Hub's time zone), not UTC: the till sells on the local date."""
    return timezone.localdate()


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


def business_jurisdiction() -> tuple[str, str | None]:
    """The business's ``(COUNTRY, REGION or None)``: the one source every calculation that names no country
    reads (sales, invoice, the API; TAX-F11). The country is Spain until the Hub receives the business's
    from its ERPlora account; the region is the one it keeps in Taxes' settings."""
    settings = TaxSettings.objects.first()
    return DEFAULT_COUNTRY, (settings.region_code or None) if settings else None


def _jurisdiction(country_code: str | None, region_code: str | None) -> tuple[str, str | None]:
    """``(COUNTRY, REGION or None)`` as the rules store them: capitals, no spaces, empty = none.

    No country is the business's jurisdiction, its region included unless one is given; naming a country
    asks for that country alone, with the region given."""
    region = (region_code or "").strip().upper() or None
    country = (country_code or "").strip().upper()
    if not country:
        country, kept = business_jurisdiction()
        region = region or kept
    return country, region


def own_tax_kind(country_code: str, region_code: str | None) -> str | None:
    """The tax of a region of ``country_code`` with one of its own (IGIC in ES-CN, IPSI in ES-CE and ES-ML), or
    ``None``: the region charges its country's VAT (a region of another country, too)."""
    kind = REGION_TAX_KINDS.get(region_code or "")
    return kind if kind and region_code.startswith(f"{country_code}-") else None


def tax_kind_of(country_code: str | None, region_code: str | None) -> str:
    """The tax family of a territory (TAX-F11): IGIC in the Canary Islands, IPSI in Ceuta and Melilla, VAT
    anywhere else. What a line with no category or rule is declared with (``Impuesto`` 03, 02 or 01)."""
    country, region = _jurisdiction(country_code or DEFAULT_COUNTRY, region_code)
    return own_tax_kind(country, region) or DEFAULT_TAX_KIND


def business_tax_kind() -> str:
    """The tax family of the business's own territory (``business_jurisdiction``)."""
    return tax_kind_of(*business_jurisdiction())


def asked_jurisdiction(country_code: str | None, region_code: str | None) -> tuple[str, str | None]:
    """The jurisdiction a reader asks for, as ``_jurisdiction``; a region of another country than the one
    it falls in is a 422 on its field, never a silent national rate."""
    country, region = _jurisdiction(country_code, region_code)
    if region and not region.startswith(f"{country}-"):
        message = str(REGION_OF_ANOTHER_COUNTRY)
        raise InvalidPayload(message, fields={"region_code": message})
    return country, region


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


def calculate_tax(
    *,
    amount: int,
    category_key: str,
    country_code: str | None = None,
    region_code: str | None = None,
    on: dt.date | None = None,
    tax_included: bool = False,
    allow_missing_rate: bool = False,
) -> dict:
    """The tax of ``amount`` cents (a ``CalculationOut``). Without a rule: 409 ``tax.no_rate``,
    unless the caller explicitly allows 0 %. A rule that cannot be read raises: nothing is guessed."""
    on = on or business_today()
    country_code, region_code = _jurisdiction(country_code, region_code)
    resolution = resolve_tax(
        category_key=category_key,
        country_code=country_code,
        region_code=region_code,
        on=on,
    )
    if resolution is None and not allow_missing_rate:
        raise Conflict(NO_RATE, code="tax.no_rate")
    components = resolution.components if resolution else []
    base, tax, quotas = split_amount(
        amount, [rule.rate_pct for rule in components], tax_included=tax_included
    )
    return {
        "base": base,
        "tax": tax,
        "total": base + tax,
        "tax_category_key": category_key,
        "tax_rate_pct": resolution.rate_pct if resolution else Decimal(0),
        "tax_country_code": country_code,
        "tax_region_code": region_code,
        "tax_rule_id": resolution.root.id if resolution else None,
        "tax_kind": resolution.tax_kind if resolution else tax_kind_of(country_code, region_code),
        "tax_operation_class": resolution.operation_class
        if resolution
        else TaxRule.OperationClass.SUBJECT,
        "tax_regime_key": resolution.regime_key if resolution else GENERAL_REGIME,
        "tax_exempt_reason": resolution.exempt_reason if resolution else "",
        "tax_included": tax_included,
        "source": "rule" if resolution else "fallback_zero",
        "date": on,
        "components": [
            {
                "rule_id": rule.id,
                "label": rule.label,
                "tax_type": rule.tax_type,
                "rate_pct": rule.rate_pct,
                "base": base,
                "tax": quota,
            }
            for rule, quota in zip(components, quotas, strict=True)
        ],
    }


@operation(
    "tax.rate.calculate",
    kind="query",
    permission="tax.view",
    input=CalculateIn,
    output=CalculationOut,
    ai={
        "description": "Resolve and calculate the tax of an amount in cents for a tax category (its key, name or "
        "alias), in the business's country and region unless a country is named: base, tax, total, the rate and "
        "the fiscal qualification of the operation. Without an applicable rule it fails instead of guessing a rate."
    },
)
def calculate(ctx: OperationContext, params: CalculateIn) -> dict:
    category = category_by_reference(params.tax_category_key)
    country_code, region_code = asked_jurisdiction(params.country_code, params.region_code)
    return calculate_tax(
        amount=params.amount,
        # A text that names no category has no rule either: tax.no_rate, never a guessed one.
        category_key=category.key if category else params.tax_category_key,
        country_code=country_code,
        region_code=region_code,
        on=params.date,
        tax_included=params.tax_included,
        allow_missing_rate=params.allow_missing_rate,
    )


# ── Categories ────────────────────────────────────────────────────────────────────────────────


def _translated(field_name: str, attribute: str) -> Case:
    """``display_name`` / ``display_description`` in SQL, in the active language, so that a filter or
    a sort reads what the column shows. A factory category reads its label; an own one, its text."""
    whens = [
        When(is_system=True, key=key, then=Value(str(getattr(label, attribute))))
        for key, label in SYSTEM_CATEGORY_LABELS.items()
        if str(getattr(label, attribute))
    ]
    return Case(*whens, default=F(field_name), output_field=CharField())


def category_row(category: TaxCategory) -> dict:
    """A ``CategoryOut`` (its texts in the active language)."""
    return {
        "id": category.id,
        "key": category.key,
        "name": category.name,
        "description": category.description,
        "display_name": category.display_name,
        "display_description": category.display_description,
        "is_system": category.is_system,
        "is_active": category.is_active,
    }


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


def _ordering(column: str, direction: str, *tie_breaks: str) -> list:
    """``column`` in ``direction`` (empty values last), then the tie-breaks, ascending."""
    expression = F(column).desc(nulls_last=True) if direction == "desc" else F(column).asc(nulls_last=True)
    return [expression, *tie_breaks]


@operation(
    "tax.category.list",
    kind="query",
    permission="tax.view",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "description": "List the active tax categories (the key products and services link to), with the "
        "rate each one has today in a country and region (the business's unless a country is named); search by "
        "key, name or description."
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    """Sorted by the column asked, ``key`` and ``id`` as the tie-break; each row with today's rate."""
    with translation.override(ctx.language):
        categories = TaxCategory.objects.filter(is_active=True).annotate(
            shown_name=_translated("name", "name"), shown_description=_translated("description", "description")
        )
        if params.search:
            categories = categories.filter(
                Q(key__icontains=params.search)
                | Q(name__icontains=params.search)
                | Q(description__icontains=params.search)
                | Q(shown_name__icontains=params.search)
                | Q(shown_description__icontains=params.search)
            )
        for column, value in (
            ("key", params.key),
            ("name", params.name),
            ("shown_name", params.display_name),
            ("shown_description", params.display_description),
        ):
            if value:
                categories = categories.filter(**{f"{column}__icontains": value})
        if params.is_system is not None:
            categories = categories.filter(is_system=params.is_system)
        column = {"display_name": "shown_name", "display_description": "shown_description"}.get(params.sort, params.sort)
        ordered = categories.order_by(*_ordering(column, params.dir, "key", "id"))
        page = list(ordered[params.offset : params.offset + params.limit])
        country_code, region_code = asked_jurisdiction(params.country_code, params.region_code)
        rates = current_rates(page, country_code, region_code, business_today())
        rows = [
            {
                **category_row(category),
                "rate_pct": rates[category.id].rate_pct if rates[category.id] else None,
                "operation_class": rates[category.id].operation_class if rates[category.id] else None,
            }
            for category in page
        ]
        return {"rows": rows, "total": categories.count(), "limit": params.limit, "offset": params.offset}


def category_by_reference(text: str) -> TaxCategory | None:
    """The category a person names: its exact key, else what ``resolve_category_text`` reads."""
    category = TaxCategory.objects.filter(key=text.strip()).first()
    if category is None:
        key, _matched_by = resolve_category_text(text)
        category = TaxCategory.objects.filter(key=key).first() if key else None
    return category


@operation(
    "tax.category.get",
    kind="query",
    permission="tax.view",
    input=CategoryGetIn,
    output=CategoryOut,
    expose_api=True,
    ai={
        "description": "Get one tax category by its key, its name or an alias, with its name in the reader's "
        "language (to check that a category exists before linking a product or a service to it)."
    },
)
def get_category(ctx: OperationContext, params: CategoryGetIn) -> dict:
    category = category_by_reference(params.key)
    if category is None:
        raise NotFound(CATEGORY_NOT_FOUND)
    with translation.override(ctx.language):
        return category_row(category)


# ── Rules ─────────────────────────────────────────────────────────────────────────────────────


def rule_row(rule: TaxRule) -> dict:
    """A ``RuleOut`` (the category's name in the active language); empty texts travel as ``None``."""
    return {
        "id": rule.id,
        "country_code": rule.country_code,
        "region_code": rule.region_code or None,
        "tax_category_key": rule.category.key,
        "tax_category_name": rule.category.display_name,
        "rate_pct": rule.rate_pct,
        "tax_type": rule.tax_type,
        "operation_class": rule.operation_class,
        "exempt_reason": rule.exempt_reason or None,
        "regime_key": rule.regime_key or None,
        "parent_id": rule.parent_id,
        "component_label": rule.component_label or None,
        "valid_from": rule.valid_from,
        "valid_to": rule.valid_to,
        "is_active": rule.is_active,
        "updated_at": rule.updated_at,
    }


def load_rule(rule_id: UUID) -> TaxRule | None:
    """A rule with its category. Not an operation: ``services.py`` returns it after a write."""
    return TaxRule.objects.select_related("category").filter(pk=rule_id).first()


#: By category, country and region; a component right after its root (the screen's default).
_GROUPED = (
    "category__key",
    "country_code",
    "region_code",
    Coalesce("parent_id", "id"),
    F("parent_id").asc(nulls_first=True),
    "id",
)
_RULE_COLUMNS = {"tax_category_key": "category__key"}


@operation(
    "tax.rule.list",
    kind="query",
    permission="tax.view",
    input=RuleListIn,
    output=RulePage,
    expose_api=True,
    ai={
        "description": "List the tax rules (the rate of a category in a country or region between two dates, "
        "with its fiscal qualification: subject, exempt, not subject or reverse charge, and its components such "
        "as the equivalence surcharge). Active ones by default; filter by country, region, category, tax type, "
        "qualification, rate or status."
    },
)
def list_rules(ctx: OperationContext, params: RuleListIn) -> dict:
    """Sorted by the column asked (by category, a component follows its root); ``id`` as the tie-break."""
    with translation.override(ctx.language):
        rules = TaxRule.objects.select_related("category")
        if params.status != "all":
            rules = rules.filter(is_active=params.status == "active")
        exact = {
            "country_code": params.country_code,
            "category__key": params.tax_category_key,
            "tax_type": params.tax_type,
            "operation_class": params.operation_class,
            "regime_key": params.regime_key,
            "parent_id": params.parent_id,
        }
        rules = rules.filter(**{column: value for column, value in exact.items() if value})
        if params.region_code:
            rules = rules.filter(region_code__icontains=params.region_code)
        if params.rate_min is not None:
            rules = rules.filter(rate_pct__gte=params.rate_min)
        if params.rate_max is not None:
            rules = rules.filter(rate_pct__lte=params.rate_max)
        if params.search:
            search = params.search.strip()
            names = Case(
                *[
                    When(category__is_system=True, category__key=key, then=Value(str(label.name)))
                    for key, label in SYSTEM_CATEGORY_LABELS.items()
                ],
                default=F("category__name"),
                output_field=CharField(),
            )
            rules = rules.annotate(category_shown_name=names).filter(
                Q(category__key__icontains=search)
                | Q(category_shown_name__icontains=search)
                | Q(country_code__icontains=search)
                | Q(region_code__icontains=search)
                | Q(operation_class__icontains=search)
            )
        if params.sort == "tax_category_key":
            first = F("category__key").desc() if params.dir == "desc" else F("category__key").asc()
            ordered = rules.order_by(first, *_GROUPED[1:])
        else:
            ordered = rules.order_by(*_ordering(_RULE_COLUMNS.get(params.sort, params.sort), params.dir, *_GROUPED))
        page = ordered[params.offset : params.offset + params.limit]
        return {
            "rows": [rule_row(rule) for rule in page],
            "total": rules.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


@operation(
    "tax.rule.status",
    kind="query",
    permission="tax.view",
    input=RuleStatusIn,
    output=RuleStatusOut,
    ai={
        "description": "Whether the business's taxes are configured: how many active root tax rules in force "
        "today match its country. Zero means the till cannot price what the business sells."
    },
)
def rule_status(ctx: OperationContext, params: RuleStatusIn) -> dict:
    """Whether the business can price a sale today: an active root rule in force in its country.

    Any qualification and any tax family count (an exempt physiotherapist, a Canary business). Without
    a country, every active root rule counts: no false «you are missing your taxes».
    """
    rules = _in_force(TaxRule.objects.filter(parent__isnull=True, is_active=True), business_today())
    if params.country_code:
        rules = rules.filter(country_code=params.country_code)
    matching = rules.count()
    return {"country_code": params.country_code, "matching_rules": matching, "configured": matching > 0}


def parent_candidates(
    country_code: str, region_code: str | None, category: TaxCategory, rate_pct: Decimal | None
) -> QuerySet:
    """The roots a component of this slot may hang from: roots of the same country, region and
    category, whatever their dates and status, that charge tax unless the component is at 0 %.

    The one predicate: ``services._coherent_parent`` accepts exactly these, and the «Root rule»
    picker offers exactly these (``tax.rule.parent_candidates``).
    """
    roots = TaxRule.objects.filter(
        parent__isnull=True,
        country_code=country_code,
        region_code=region_code or "",
        category=category,
    )
    if rate_pct is None or rate_pct != 0:
        roots = roots.filter(operation_class=TaxRule.OperationClass.SUBJECT)
    return roots


@operation(
    "tax.rule.parent_candidates",
    kind="query",
    permission="tax.view",
    input=RuleParentIn,
    output=RulePage,
    ai={
        "description": "List the root tax rules a component (such as the equivalence surcharge) may hang from "
        "in a country, region and category: the ones tax.rule.create accepts as its parent_id."
    },
)
def list_parent_candidates(ctx: OperationContext, params: RuleParentIn) -> dict:
    """Active first, the newest first; an unknown category has none."""
    with translation.override(ctx.language):
        category = category_by_reference(params.tax_category_key)
        if category is None:
            return {"rows": [], "total": 0, "limit": params.limit, "offset": params.offset}
        roots = parent_candidates(params.country_code, params.region_code, category, params.rate_pct)
        ordered = roots.select_related("category").order_by(
            F("is_active").desc(), F("valid_from").desc(nulls_last=True), "id"
        )
        page = ordered[params.offset : params.offset + params.limit]
        return {
            "rows": [rule_row(rule) for rule in page],
            "total": roots.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


@operation(
    "tax.rule.countries",
    kind="query",
    permission="tax.view",
    input=RuleCountriesIn,
    output=RuleCountriesOut,
    ai={"description": "List the countries the business has tax rules for (all of them, or only active or deactivated)."},
)
def rule_countries(ctx: OperationContext, params: RuleCountriesIn) -> dict:
    rules = TaxRule.objects.all()
    if params.status != "all":
        rules = rules.filter(is_active=params.status == "active")
    return {"countries": list(rules.order_by("country_code").values_list("country_code", flat=True).distinct())}


# ── Aliases ───────────────────────────────────────────────────────────────────────────────────


def alias_row(alias: TaxAlias) -> dict:
    return {
        "id": alias.id,
        "alias": alias.alias,
        "tax_category_key": alias.category.key,
        "tax_category_name": alias.category.display_name,
        "source": alias.source,
        "is_active": alias.is_active,
    }


_ALIAS_COLUMNS = {"tax_category_key": "category__key"}


@operation(
    "tax.alias.list",
    kind="query",
    permission="tax.view",
    input=AliasListIn,
    output=AliasPage,
    expose_api=True,
    ai={
        "description": "List the active category aliases (an outside text such as «beer» or «IVA 10» → the key "
        "of a tax category) that the CSV importer of inventory recognises."
    },
)
def list_aliases(ctx: OperationContext, params: AliasListIn) -> dict:
    """Sorted by the column asked, ``alias`` and ``id`` as the tie-break."""
    with translation.override(ctx.language):
        aliases = TaxAlias.objects.select_related("category").filter(is_active=True)
        if params.search:
            search = params.search.strip()
            aliases = aliases.filter(Q(alias__icontains=search) | Q(category__key__icontains=search))
        if params.alias:
            aliases = aliases.filter(alias__icontains=params.alias.strip())
        if params.tax_category_key:
            aliases = aliases.filter(category__key=params.tax_category_key)
        if params.source:
            aliases = aliases.filter(source=params.source)
        column = _ALIAS_COLUMNS.get(params.sort, params.sort)
        page = aliases.order_by(*_ordering(column, params.dir, "alias", "id"))[
            params.offset : params.offset + params.limit
        ]
        return {
            "rows": [alias_row(alias) for alias in page],
            "total": aliases.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


def resolve_category_text(text: str) -> tuple[str | None, str | None]:
    """``(category key, matched by)`` of an outside text, or ``(None, None)``; never a similar one.

    Compared normalised, against the active categories and aliases, in this order: the keys; the
    names, the stored ones and the factory categories' in every language of the Hub; the aliases.
    """
    text = normalize_text(text)
    categories = TaxCategory.objects.filter(is_active=True)
    if categories.filter(key=text).exists():
        return text, "key"
    for category in categories.only("key", "name").order_by("key", "id"):
        if normalize_text(category.name) == text:
            return category.key, "name"
    system_keys = set(categories.filter(is_system=True).values_list("key", flat=True))
    for language, _language_name in settings.LANGUAGES:
        with translation.override(language):
            for key, label in SYSTEM_CATEGORY_LABELS.items():
                if key in system_keys and normalize_text(str(label.name)) == text:
                    return key, "name"
    alias = TaxAlias.objects.select_related("category").filter(alias=text, is_active=True, category__is_active=True).first()
    if alias is not None:
        return alias.category.key, "alias"
    return None, None


@operation(
    "tax.alias.resolve",
    kind="query",
    permission="tax.view",
    input=AliasResolveIn,
    output=AliasResolveOut,
    expose_api=True,
    ai={
        "description": "Read an outside text (a CSV cell such as «IVA 10», «beer» or «comida») as a tax "
        "category: by its key, its name in any language, or a learned alias. Nothing when nothing matches."
    },
)
def resolve_alias(ctx: OperationContext, params: AliasResolveIn) -> dict:
    key, matched_by = resolve_category_text(params.text)
    return {"text": params.text, "tax_category_key": key, "matched_by": matched_by}


# ── The business's tax settings (TAX-F11) ──────────────────────────────────────────────────────


def settings_row(settings: TaxSettings | None) -> dict:
    country, _region = business_jurisdiction()
    region = (settings.region_code or None) if settings else None
    return {
        "country_code": country,
        "region_code": region,
        "regions": list(TAX_REGIONS.get(country, ())),
        "tax_kind": tax_kind_of(country, region),
        "updated_at": settings.updated_at if settings else None,
    }


@operation(
    "tax.settings.get",
    kind="query",
    permission="tax.view",
    input=SettingsGetIn,
    output=TaxSettingsOut,
    ai={
        "description": "Read the business's tax region and country: the jurisdiction every sale and invoice is "
        "charged in. ES-CN is the Canary Islands (IGIC), ES-CE Ceuta and ES-ML Melilla (IPSI); empty is the "
        "whole country (VAT). Also the regions it may keep."
    },
)
def get_settings(ctx: OperationContext, params: SettingsGetIn) -> dict:
    return settings_row(TaxSettings.objects.first())
