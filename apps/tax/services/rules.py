"""Creating tax rules, one by one or in a batch (TAX-F04, F05, F06, F11, F12)."""

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import TaxCategory, TaxRule
from apps.tax.queries.categories import CATEGORY_NOT_FOUND
from apps.tax.queries.jurisdiction import tax_kind_of
from apps.tax.queries.naming import category_by_reference
from apps.tax.queries.rules import parent_candidates, rule_row
from apps.tax.schemas.rules import RuleBulkIn, RuleBulkOut, RuleFields, RuleIn, RuleOut
from apps.tax.services.categories import _category
from apps.tax.services.overlaps import RULE_OVERLAPS, _lock, _overlapping, _refuse_overlap

CENTS = Decimal("0.01")

RULE_INCOHERENT = _(
    "The component could not be created: it must hang from a root rule with the same country, region and "
    "category, and a root that charges no tax admits no component with a rate."
)
RULE_EXISTS = _(
    "There is already a rule of this country, region and category from that day, perhaps deactivated: "
    "reactivate it or start this one another day."
)


def _has_twin(data: RuleFields, category: TaxCategory) -> bool:
    """Whether a root of the same country, region, category and first day exists, active or not
    (the natural key ``tax_rule_root_natural_key``; an empty first day is «since always»)."""
    first_day = {"valid_from": data.valid_from} if data.valid_from else {"valid_from__isnull": True}
    return TaxRule.objects.filter(
        parent__isnull=True,
        country_code=data.country_code,
        region_code=data.region_code or "",
        category=category,
        **first_day,
    ).exists()


def _new_rule(
    data: RuleFields,
    category: TaxCategory,
    parent: TaxRule | None = None,
    label: str = "",
) -> TaxRule:
    """The rule, not saved yet: its checks run first."""
    exempt = data.operation_class == TaxRule.OperationClass.EXEMPT
    return TaxRule(
        category=category,
        country_code=data.country_code,
        region_code=data.region_code or "",
        # As stored (two decimals): the row returned and the event say what the database keeps.
        rate_pct=data.rate_pct.quantize(CENTS),
        # No family said: the one of the rule's territory (TAX-F11), never VAT in the Canary Islands.
        tax_type=data.tax_type or tax_kind_of(data.country_code, data.region_code),
        operation_class=data.operation_class,
        # The cause only means something on an exempt rule.
        exempt_reason=(data.exempt_reason or "") if exempt else "",
        regime_key=data.regime_key or "",
        parent=parent,
        component_label=label,
        valid_from=data.valid_from,
        valid_to=data.valid_to,
    )


def _created(ctx: OperationContext, rule: TaxRule) -> None:
    record_event(
        ctx,
        events.RULE_CREATED,
        {
            "id": str(rule.id),
            "country_code": rule.country_code,
            "region_code": rule.region_code or None,
            "tax_category_key": rule.category.key,
            "rate_pct": str(rule.rate_pct),
        },
    )


def _coherent_parent(data: RuleIn, category: TaxCategory) -> TaxRule:
    """The root a component hangs from: a root of the same slot, which charges tax if it carries a rate."""
    # The predicate the «Root rule» picker shows too (queries.rules.parent_candidates).
    parent = (
        parent_candidates(data.country_code, data.region_code, category, data.rate_pct)
        .filter(pk=data.parent_id)
        .first()
    )
    if parent is None:
        raise Conflict(
            RULE_INCOHERENT,
            code="tax.rule_incoherent",
            fields={"parent_id": str(RULE_INCOHERENT)},
        )
    return parent


@operation(
    "tax.rule.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=RuleIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "create a 21 % VAT rule for books in Spain",
                "add a tax rule of 10 % for food from 1 January",
                "new exempt tax rule for medical services in Spain",
            ),
            "es": (
                "crea una regla de IVA del 10 % para la comida en España",
                "añade una regla fiscal exenta para los servicios médicos",
                "nueva regla de impuestos del 4 % para los libros desde el 1 de enero",
            ),
        },
        "description": "Create a tax rule: the rate in % of a tax category in a country (or one of its regions) "
        "between two dates, with its fiscal qualification (operation_class: subject, or exempt, not subject or "
        "reverse charge, which charge no tax and take rate 0; exempt_reason, regime_key). With parent_id it is "
        "a component, such as the equivalence surcharge, of that root rule. Two active rules of the same country, "
        "region and category cannot apply on the same day: end the old one the day before (tax.rule.end).",
        "risk": "high", "does": ("set", "update"),  # A rule is never changed: creating one sets or changes a rate.
    },
)
def create_rule(ctx: OperationContext, data: RuleIn) -> dict:
    category = _category(data.tax_category_key)
    _lock([category])
    parent = _coherent_parent(data, category) if data.parent_id else None
    rule = _new_rule(data, category, parent, data.component_label or "")
    # An active rule in force those days is an overlap (also when it starts the same day); a
    # deactivated one starting that day still holds the root's natural key.
    _refuse_overlap(rule, "valid_from")
    if parent is None and _has_twin(data, category):
        raise Conflict(RULE_EXISTS, code="tax.rule_exists", fields={"valid_from": str(RULE_EXISTS)})
    rule.save()
    _created(ctx, rule)
    return rule_row(rule)


@operation(
    "tax.rule.bulk_create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=RuleBulkIn,
    output=RuleBulkOut,
    ai={
        "asks": {
            "en": (
                "create the 2026 VAT rates of Portugal in one go",
                "import several tax rules at once",
                "add these three tax rules together: books 4 %, food 10 % and general 21 %",
            ),
            "es": (
                "crea de una vez todas las reglas de IVA de Portugal para 2026",
                "importa varias reglas fiscales en un lote",
                "añade juntas tres reglas de impuestos: libros al 4 %, comida al 10 % y general al 21 %",
            ),
        },
        "description": "Create up to 100 root tax rules at once (for example the 2026 VAT rates of a country), "
        "each with the checks of tax.rule.create: either all are saved or none, and every refusal names its "
        "row. Components are created one by one with tax.rule.create.",
        "risk": "high",
    },
)
def bulk_create_rules(ctx: OperationContext, data: RuleBulkIn) -> dict:
    categories: list[TaxCategory | None] = [
        category_by_reference(row.tax_category_key) for row in data.rules
    ]
    unknown = {
        f"rules.{index}.tax_category_key": str(CATEGORY_NOT_FOUND)
        for index, category in enumerate(categories)
        if category is None
    }
    if unknown:
        raise InvalidPayload(
            str(CATEGORY_NOT_FOUND), code="invalid_field", fields=unknown
        )
    _lock(list({category.pk: category for category in categories}.values()))
    created, twins, overlaps = [], {}, {}
    for index, (row, category) in enumerate(zip(data.rules, categories, strict=True)):
        rule = _new_rule(row, category)
        twin = _has_twin(row, category)
        if _overlapping(rule) is not None:  # earlier rows of this batch are already saved
            overlaps[f"rules.{index}.valid_from"] = str(RULE_OVERLAPS)
        elif twin:
            twins[f"rules.{index}.valid_from"] = str(RULE_EXISTS)
        if not twin:  # a twin would break the natural key; the batch is refused anyway
            rule.save()
            created.append(rule)
    # Raising rolls the whole batch back: all or none, every refused row named.
    if overlaps:
        raise Conflict(RULE_OVERLAPS, code="tax.rule_overlaps", fields={**overlaps, **twins})
    if twins:
        raise Conflict(RULE_EXISTS, code="tax.rule_exists", fields=twins)
    for rule in created:
        _created(ctx, rule)
    return {"rules": [rule_row(rule) for rule in created]}
