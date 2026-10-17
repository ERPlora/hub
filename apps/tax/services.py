"""Write operations of the tax app: one operation = one transaction, with its events in the outbox.

A rule is never edited nor deleted: it is created, given an end date, deactivated or reactivated.
Every write that can make two active root rules of the same slot (country, region, category) apply on
the same day locks the category's row first (``select_for_update``), so two people saving at once are
queued, and the second one's check sees the first one's rule (taxes#66, #69). The refusals carry the
field they are about, so the screen puts them next to it.
"""

from collections.abc import Callable
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import ACTOR_MAX_LENGTH, TaxAlias, TaxCategory, TaxRule, TaxSettings
from apps.tax.queries import (
    CATEGORY_NOT_FOUND,
    RULE_NOT_FOUND,
    alias_row,
    business_jurisdiction,
    business_today,
    category_by_reference,
    category_row,
    load_rule,
    parent_candidates,
    rule_row,
    settings_row,
    tax_kind_of,
)
from apps.tax.schemas import (
    REGION_NOT_AVAILABLE,
    TAX_REGIONS,
    AliasIn,
    AliasOut,
    CategoryIn,
    CategoryOut,
    RuleBulkIn,
    RuleBulkOut,
    RuleEndIn,
    RuleFields,
    RuleIn,
    RuleOut,
    RuleRefIn,
    TaxSettingsIn,
    TaxSettingsOut,
)

CENTS = Decimal("0.01")

CATEGORY_EXISTS = _("There is already a tax category with that key.")
ALIAS_EXISTS = _("That alias already exists.")
RULE_OVERLAPS = _(
    "It overlaps another active rule of this country, region and category: two rates cannot apply on the "
    "same day. End that rule the day before this one starts, or deactivate it."
)
RULE_INCOHERENT = _(
    "The component could not be created: it must hang from a root rule with the same country, region and "
    "category, and a root that charges no tax admits no component with a rate."
)
RULE_END_INVALID = _("That rule cannot end before the day it starts.")
RULE_EXISTS = _(
    "There is already a rule of this country, region and category from that day, perhaps deactivated: "
    "reactivate it or start this one another day."
)
RULE_ALREADY_ACTIVE = _("That rule is already active.")
RULE_ALREADY_INACTIVE = _("That rule is already deactivated.")


# ── Categories ────────────────────────────────────────────────────────────────────────────────


@operation(
    "tax.category.create",
    kind="command",
    permission="tax.manage",
    input=CategoryIn,
    output=CategoryOut,
    ai={
        "description": "Create a tax category with its key (the one products and services link to, such as "
        "product.books) and its name. It brings no rate: create its rule next.",
        "risk": "normal",
    },
)
def create_category(ctx: OperationContext, data: CategoryIn) -> dict:
    try:
        with transaction.atomic():
            category = TaxCategory.objects.create(**data.model_dump())
    except IntegrityError:  # the key is the only unique field
        raise Conflict(
            CATEGORY_EXISTS,
            code="tax.category_exists",
            fields={"key": str(CATEGORY_EXISTS)},
        ) from None
    record_event(
        ctx, events.CATEGORY_CREATED, {"id": str(category.id), "key": category.key}
    )
    return category_row(category)


def _category(reference: str, field: str = "tax_category_key") -> TaxCategory:
    category = category_by_reference(reference)
    if category is None:
        raise InvalidPayload(
            str(CATEGORY_NOT_FOUND),
            code="invalid_field",
            fields={field: str(CATEGORY_NOT_FOUND)},
        )
    return category


# ── Aliases ───────────────────────────────────────────────────────────────────────────────────


@operation(
    "tax.alias.create",
    kind="command",
    permission="tax.manage",
    input=AliasIn,
    output=AliasOut,
    ai={
        "description": "Teach an outside text (a CSV cell such as «cerveza» or «IVA 10») to mean a tax category, "
        "so the next import of inventory recognises it. Kept lowercase with single spaces.",
        "risk": "normal",
    },
)
def create_alias(ctx: OperationContext, data: AliasIn) -> dict:
    category = _category(data.tax_category_key)
    try:
        with transaction.atomic():
            alias = TaxAlias.objects.create(
                alias=data.alias, category=category, source=data.source
            )
    except IntegrityError:  # the alias is the only unique field
        raise Conflict(
            ALIAS_EXISTS, code="tax.alias_exists", fields={"alias": str(ALIAS_EXISTS)}
        ) from None
    record_event(
        ctx,
        events.ALIAS_CREATED,
        {"id": str(alias.id), "alias": alias.alias, "tax_category_key": category.key},
    )
    return alias_row(alias)


# ── Rules ─────────────────────────────────────────────────────────────────────────────────────


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
    # The predicate the «Root rule» picker shows too (queries.parent_candidates).
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
    permission="tax.manage",
    input=RuleIn,
    output=RuleOut,
    ai={
        "description": "Create a tax rule: the rate in % of a tax category in a country (or one of its regions) "
        "between two dates, with its fiscal qualification (operation_class: subject, or exempt, not subject or "
        "reverse charge, which charge no tax and take rate 0; exempt_reason, regime_key). With parent_id it is "
        "a component, such as the equivalence surcharge, of that root rule. Two active rules of the same country, "
        "region and category cannot apply on the same day: end the old one the day before (tax.rule.end).",
        "risk": "high",
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
    permission="tax.manage",
    input=RuleBulkIn,
    output=RuleBulkOut,
    ai={
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


def _named_rule(
    reference: RuleRefIn, pick: Callable[[list[TaxRule]], TaxRule | None]
) -> TaxRule:
    """The rule a person names, locked with its category: by its id, or by its slot through ``pick``."""
    if reference.id is not None:
        rule = load_rule(reference.id)
    else:
        category = category_by_reference(reference.tax_category_key)
        slot = TaxRule.objects.select_related("category").filter(
            parent__isnull=True,
            country_code=reference.country_code,
            region_code=reference.region_code or "",
            category=category,
        )
        rule = pick(list(slot)) if category else None
    if rule is None:
        raise NotFound(RULE_NOT_FOUND)
    _lock([rule.category])
    return (
        # ``of=self``: the category is locked by ``_lock`` alone, the one place that orders the locks.
        TaxRule.objects.select_for_update(of=("self",)).select_related("category").get(pk=rule.pk)
    )


def _newest(rules: list[TaxRule]) -> TaxRule | None:
    """The one with the newest start (an empty start is the oldest), then the lowest id."""
    return min(
        rules,
        key=lambda r: (-(r.valid_from.toordinal() if r.valid_from else 0), r.id.int),
        default=None,
    )


def _in_force_today(rules: list[TaxRule]) -> TaxRule | None:
    today = business_today()
    return _newest(
        [rule for rule in rules if rule.is_active and rule.in_force_on(today)]
    )


def _latest_deactivated(rules: list[TaxRule]) -> TaxRule | None:
    """The one deactivated most recently (its last change, ``updated_at``), then the highest id."""
    deactivated = [rule for rule in rules if not rule.is_active]
    return max(deactivated, key=lambda rule: (rule.updated_at, rule.id.int), default=None)


@operation(
    "tax.rule.end",
    kind="command",
    permission="tax.manage",
    input=RuleEndIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "description": "Set the last day (inclusive) a tax rule applies, named by its id or by its country, "
        "region and category (the rule in force today). This is how a rate change is scheduled: end the current "
        "rule the day before the new rate starts, then create the new rule from that day. Issued invoices do "
        "not change.",
        "risk": "high",
    },
)
def end_rule(ctx: OperationContext, data: RuleEndIn) -> dict:
    rule = _named_rule(data, _in_force_today)
    if rule.valid_from is not None and data.valid_to < rule.valid_from:
        raise Conflict(
            RULE_END_INVALID,
            code="tax.rule_end_invalid",
            fields={"valid_to": str(RULE_END_INVALID)},
        )
    if rule.valid_to != data.valid_to:
        rule.valid_to = data.valid_to
        _refuse_overlap(rule, "valid_to")
        rule.save(update_fields=["valid_to", "updated_at"])
        record_event(
            ctx,
            events.RULE_ENDED,
            {"id": str(rule.id), "valid_to": data.valid_to.isoformat()},
        )
    return rule_row(rule)


def _switch(ctx: OperationContext, rule: TaxRule, active: bool) -> dict:
    if rule.is_active == active:
        message, code = (
            (RULE_ALREADY_ACTIVE, "tax.rule_already_active")
            if active
            else (RULE_ALREADY_INACTIVE, "tax.rule_already_inactive")
        )
        raise Conflict(message, code=code)
    rule.is_active = active
    if active:
        _refuse_overlap(rule, None)
    rule.save(update_fields=["is_active", "updated_at"])
    record_event(
        ctx,
        events.RULE_ACTIVATED if active else events.RULE_DEACTIVATED,
        {"id": str(rule.id)},
    )
    return rule_row(rule)


@operation(
    "tax.rule.deactivate",
    kind="command",
    permission="tax.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "description": "Deactivate a tax rule so it no longer applies to new operations, named by its id or by its "
        "country, region and category (the rule in force today). Its rate, dates and components are kept and "
        "issued invoices do not change; tax.rule.activate brings it back.",
        "risk": "high",
    },
)
def deactivate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch(ctx, _named_rule(data, _in_force_today), active=False)


@operation(
    "tax.rule.activate",
    kind="command",
    permission="tax.manage",
    input=RuleRefIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "description": "Bring a deactivated tax rule back so it applies to new operations again, named by its id "
        "or by its country, region and category (the most recent deactivated one). Refused if it would now "
        "overlap another active rule of the same country, region and category.",
        "risk": "high",
    },
)
def activate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch(ctx, _named_rule(data, _latest_deactivated), active=True)



# ── The business's tax settings (TAX-F11) ──────────────────────────────────────────────────────


def _locked_settings(ctx: OperationContext) -> TaxSettings:
    """The business's settings row, locked; created (the whole country) the first time."""
    settings = TaxSettings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with transaction.atomic():
            return TaxSettings.objects.create(updated_by=_actor(ctx))
    except IntegrityError:
        return TaxSettings.objects.select_for_update().get()


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH] if ctx.actor is not None else ""


@operation(
    "tax.settings.update",
    kind="command",
    permission="tax.manage",
    input=TaxSettingsIn,
    output=TaxSettingsOut,
    ai={
        "description": "Keep the business's tax region: ES-CN (Canary Islands, IGIC), ES-CE (Ceuta, IPSI), ES-ML "
        "(Melilla, IPSI), or empty for the whole country (VAT). From then on every sale and invoice charges the "
        "rule of that region; a category without one cannot be charged there until it has it (the national VAT "
        "never applies in those territories).",
        "risk": "high",
    },
)
def update_settings(ctx: OperationContext, data: TaxSettingsIn) -> dict:
    country, _kept = business_jurisdiction()
    region = data.region_code
    if region and region not in TAX_REGIONS.get(country, ()):
        message = str(REGION_NOT_AVAILABLE)
        raise InvalidPayload(message, code="tax.region_not_available", fields={"region_code": message})
    settings = _locked_settings(ctx)
    if settings.region_code != (region or ""):
        settings.region_code = region or ""
        settings.updated_by = _actor(ctx)
        settings.save(update_fields=["region_code", "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"country_code": country, "region_code": region})
    return settings_row(settings)
