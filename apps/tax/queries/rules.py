"""The tax rules: one rule with its name, the list of the Rules screen, whether the business can price a sale today
(TAX-F17), the roots a component may hang from and the countries the rules are for."""

from decimal import Decimal
from uuid import UUID

from babel.numbers import format_percent
from django.db.models import Case, CharField, F, Q, QuerySet, Value, When
from django.db.models.functions import Coalesce
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.tax.models import SYSTEM_CATEGORY_LABELS, TaxCategory, TaxRule
from apps.tax.queries.calculation import _HUNDRED
from apps.tax.queries.jurisdiction import business_jurisdiction, business_today
from apps.tax.queries.naming import category_by_reference
from apps.tax.queries.resolution import _in_force
from apps.tax.schemas import (
    FACTORY_COUNTRIES,
    RuleCountriesIn,
    RuleCountriesOut,
    RuleGetIn,
    RuleListIn,
    RuleNamedOut,
    RulePage,
    RuleParentIn,
    RuleStatusIn,
    RuleStatusOut,
)
from base.business import babel_locale, country_name
from base.ordering import list_order

RULE_NOT_FOUND = _("This tax rule no longer exists.")


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


def rule_label(rule: TaxRule) -> str:
    """How a person names ``rule``, in the active language: its category, a component's label, its country (and its
    region) and its rate, as the Rules screen tells one from another («Cervezas · España (ES-CN) · 7 %»)."""
    language = translation.get_language()
    place = country_name(rule.country_code, language)
    if rule.region_code:
        place = f"{place} ({rule.region_code})"
    rate = format_percent(rule.rate_pct.normalize() / _HUNDRED, locale=babel_locale(language), decimal_quantization=False)
    return " · ".join(part for part in (rule.category.display_name, rule.component_label, place, rate) if part)


@operation(
    "tax.rule.get",
    kind="query",
    permission="tax.view",
    input=RuleGetIn,
    output=RuleNamedOut,
    ai=INTERNAL,
)
def get_rule(ctx: OperationContext, params: RuleGetIn) -> dict:
    """One rule, active or deactivated, with its name: what names a rule on the assistant's card (``schemas.A_RULE``);
    the model and the screens read the rules by their list."""
    rule = load_rule(params.id)
    if rule is None:
        raise NotFound(RULE_NOT_FOUND)
    with translation.override(ctx.language):
        return {**rule_row(rule), "label": rule_label(rule)}


#: By category, country and region; a component right after its root (the screen's default).
_GROUPED = (
    "category__key",
    "country_code",
    "region_code",
    Coalesce("parent_id", "id"),
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
        "asks": {
            "en": (
                "show me the tax rules",
                "which VAT rates apply in Spain?",
                "list the deactivated tax rules of Portugal",
            ),
            "es": (
                "muéstrame las reglas de impuestos",
                "¿a qué tipo está hoy el IVA de los libros en España?",
                "¿qué porcentaje tiene cada regla de IVA de Portugal y desde cuándo?",
            ),
        },
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
        column = _RULE_COLUMNS.get(params.sort, params.sort)
        keys = list_order(column, *_GROUPED, descending=params.dir == "desc", nulls_last=True)
        # A component comes right under its root whichever the direction: that is how it is recognised (TAX-F03).
        ordered = rules.order_by(*keys[:-1], F("parent_id").asc(nulls_first=True), keys[-1])
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
        "asks": {
            "en": (
                "do I have the tax rules the till needs to start selling?",
                "does the till have the tax rules it needs to sell?",
                "how many tax rules are in force in Spain today?",
            ),
            "es": (
                "¿le falta alguna regla de impuestos al negocio para poder vender?",
                "¿hay alguna regla de IVA en vigor para poder cobrar?",
                "¿cuántas reglas fiscales están en vigor hoy en España?",
            ),
        },
        "description": "Whether the business's taxes are configured: how many active root tax rules of its country "
        "(or of the one named) are in force today, and whether Taxes brings that country's rules ready (only "
        "Spain's). Zero means the till cannot price what the business sells until it creates them in Rules."
    },
)
def rule_status(ctx: OperationContext, params: RuleStatusIn) -> dict:
    """Whether the business can price a sale today: an active root rule in force in its country (TAX-F17).

    Any qualification and any tax family count (an exempt physiotherapist, a Canary business). Only that
    country's: a business of another country also keeps Spain's factory rules, which never price its sales
    (hub#996), so they never tell it its taxes are set up.
    """
    country = params.country_code or business_jurisdiction()[0]
    rules = _in_force(TaxRule.objects.filter(parent__isnull=True, is_active=True), business_today())
    matching = rules.filter(country_code=country).count()
    return {
        "country_code": country,
        "matching_rules": matching,
        "configured": matching > 0,
        "factory_rules": country in FACTORY_COUNTRIES,
    }


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
        "asks": {
            "en": (
                "which rule can the equivalence surcharge hang from?",
                "list the main VAT rules a surcharge can go under in Spain",
                "what parent rules are there for a component of the books category?",
            ),
            "es": (
                "¿bajo qué regla raíz puedo poner el recargo de equivalencia de la cerveza?",
                "lista las reglas principales que admiten un recargo en España",
                "¿qué reglas pueden ser padre de un componente de la categoría de libros?",
            ),
        },
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
    ai={
        "asks": {
            "en": (
                "which countries do I have tax rules for?",
                "in which countries are my VAT rules deactivated?",
                "show the countries of my VAT rules",
            ),
            "es": (
                "¿de qué países hay reglas fiscales en el negocio?",
                "¿qué países tienen alguna regla de IVA desactivada?",
                "lista los países con impuestos configurados",
            ),
        },
        "description": "List the countries the business has tax rules for (all of them, or only active or "
        "deactivated).",
    },
)
def rule_countries(ctx: OperationContext, params: RuleCountriesIn) -> dict:
    rules = TaxRule.objects.all()
    if params.status != "all":
        rules = rules.filter(is_active=params.status == "active")
    return {"countries": list(rules.order_by("country_code").values_list("country_code", flat=True).distinct())}
