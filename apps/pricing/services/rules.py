"""Writes of the discount rules: create and edit one, deactivate and activate it."""

from typing import Any

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.inventory.queries.reads import find_category
from apps.pricing import events
from apps.pricing.models import DiscountRule
from apps.pricing.queries.other_apps import call_service
from apps.pricing.queries.reads import find_rule
from apps.pricing.queries.rows import rule_row, snapshot_values
from apps.pricing.schemas import SCOPE_TARGETS, TYPE_VALUES, RuleIn, RuleOut, RulePatchIn, RuleRefIn, rule_problems
from apps.pricing.services.writes import _actor, _constraint, _field_error, _group_held, _group_id, _held_product
from base import operations as platform

DUPLICATE_RULE_CODE = _("A discount rule with that code already exists. Pick a different code.")
RULE_ALREADY_INACTIVE = _("That discount rule is already deactivated.")
RULE_ALREADY_ACTIVE = _("That discount rule is already active.")
RULE_GROUP_DELETED = _(
    "This rule's customer group no longer exists: choose another group or take it off before activating it."
)

RULE_CODE_UNIQUE = "pricing_rule_code_unique"


def _refuse(problems: dict[str, str]) -> None:
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code="invalid_field", fields=problems)


def _tiers(tiers) -> list[dict]:
    return [{"min_quantity": str(tier["min_quantity"]), "percent": str(tier["percent"])} for tier in tiers or []]


def _set_value(rule: DiscountRule, values: dict[str, Any]) -> None:
    """The value(s) of the rule's type; those of the other types, empty."""
    for names in TYPE_VALUES.values():
        for name in names:
            mine = name in TYPE_VALUES[rule.rule_type]
            if name == "tiers":
                rule.tiers = _tiers(values.get("tiers")) if mine else []
            else:
                setattr(rule, name, values.get(name) if mine else None)


def _set_target(ctx: OperationContext, rule: DiscountRule, values: dict[str, Any]) -> None:
    """The category, product or service of the rule's scope (by id or text), the first two held until this
    write ends; the others, empty."""
    rule.category, rule.product, rule.service_id, rule.service_name = None, None, None, ""
    if rule.applies_to not in SCOPE_TARGETS:
        return
    field, id_key, text_key = SCOPE_TARGETS[rule.applies_to]
    target_id, said = values.get(id_key), values.get(text_key)
    try:
        if rule.applies_to == DiscountRule.Scope.CATEGORY:
            rule.category = find_category(target_id, said, hold=True)
        elif rule.applies_to == DiscountRule.Scope.PRODUCT:
            rule.product = _held_product(target_id, said)
        else:
            service = call_service(ctx, target_id, said)
            rule.service_id, rule.service_name = service.id, service.name
    except (NotFound, Conflict) as error:
        if error.code == "pricing.services_unavailable":
            raise
        raise _field_error(error, id_key if target_id is not None else field) from None


def _save_rule(rule: DiscountRule) -> None:
    try:
        with atomic():
            rule.save()
    except IntegrityError as error:
        if _constraint(error) == RULE_CODE_UNIQUE:
            raise Conflict(
                str(DUPLICATE_RULE_CODE), code="pricing.duplicate_code", fields={"code": str(DUPLICATE_RULE_CODE)}
            ) from None
        raise


@operation(
    "pricing.rule.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=RuleIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "create a 3-for-2 promotion on toasts",
                "I want an automatic 10 % discount on toasts for partners",
                "new reduction: toasts 50 cents cheaper from three on",
            ),
            "es": (
                "crea una promoción 3x2 en las tostadas",
                "quiero un descuento automático del 10 % en tostadas para socios",
                "nueva rebaja: 50 céntimos menos en las tostadas a partir de tres",
            ),
        },
        "description": "Create an automatic discount rule for a line: its code and name, its type with its value "
        "(percent: a percent; fixed: cents off each unit; buy_x_get_y: buy and free units; tiered: percents by "
        "quantity), what it applies to (all, products, services, a category, a product or a service, by name), and if "
        "wanted a customer group, a minimum quantity, first and last day and a priority. A line gets only the rule that "
        "takes the most off, so a lower discount for what a rule already covers is a change of that rule.",
        "risk": "normal",
    },
)
def create_rule(ctx: OperationContext, data: RuleIn) -> dict:
    values = data.model_dump()
    _refuse(rule_problems(values))
    actor = _actor(ctx)
    rule = DiscountRule(
        code=data.code,
        name=data.name,
        rule_type=data.rule_type,
        applies_to=data.applies_to,
        min_quantity=data.min_quantity,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        priority=data.priority,
        created_by=actor,
        updated_by=actor,
    )
    _set_value(rule, values)
    _set_target(ctx, rule, values)
    rule.customer_group_id = _group_id(data.customer_group_id, data.customer_group)
    _save_rule(rule)
    record_event(ctx, events.RULE_CREATED, {"id": str(rule.id), "code": rule.code})
    return rule_row(rule, platform.business_currency(ctx.scope))


_TARGET_KEYS = {key for _field, id_key, text_key in SCOPE_TARGETS.values() for key in (id_key, text_key)}
_PLAIN = ("code", "name", "min_quantity", "valid_from", "valid_until", "priority")
_COMPARED = (
    *_PLAIN,
    "rule_type",
    "applies_to",
    "percent",
    "amount",
    "buy_quantity",
    "get_quantity",
    "tiers",
    "category_id",
    "product_id",
    "service_id",
    "customer_group_id",
)


@operation(
    "pricing.rule.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=RulePatchIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "change the summer promotion to 20 %",
                "the summer promotion now needs a minimum of two",
                "raise the reduction of the summer promotion",
            ),
            "es": (
                "cambia la promoción de verano al 20 %",
                "la promoción de verano ahora exige un mínimo de dos",
                "sube la rebaja de la promoción de verano",
            ),
        },
        "description": "Change a discount rule, the discount a product or a category gets by itself on every sale (the "
        "coffee discount), named by its id, code or name: only the fields sent. A new type asks for its value; a new "
        "target, for what it applies to. null takes the group, the minimum quantity or a day off.",
        "risk": "normal",
    },
)
def update_rule(ctx: OperationContext, data: RulePatchIn) -> dict:  # noqa: C901
    rule = find_rule(data.id, data.rule, lock=True)
    sent = data.model_fields_set - {"id", "rule"}
    before = {name: getattr(rule, name) for name in _COMPARED}
    merged = snapshot_values(rule)
    if "rule_type" in sent and data.rule_type != rule.rule_type:
        for name in (name for names in TYPE_VALUES.values() for name in names):
            if name not in sent:
                merged[name] = [] if name == "tiers" else None
    if ("applies_to" in sent and data.applies_to != rule.applies_to) or sent & _TARGET_KEYS:
        for key in _TARGET_KEYS:
            merged[key] = None
    dumped = data.model_dump(include=sent)
    merged.update(dumped)
    _refuse(rule_problems(merged))
    for name in _PLAIN:
        if name in sent:
            setattr(rule, name, dumped[name])
    rule.rule_type, rule.applies_to = merged["rule_type"], merged["applies_to"]
    _set_value(rule, merged)
    if sent & ({"applies_to"} | _TARGET_KEYS):
        _set_target(ctx, rule, merged)
    if sent & {"customer_group_id", "customer_group"}:
        rule.customer_group_id = _group_id(data.customer_group_id, data.customer_group)
    if {name: getattr(rule, name) for name in _COMPARED} != before:
        rule.updated_by = _actor(ctx)
        _save_rule(rule)
        record_event(ctx, events.RULE_UPDATED, {"id": str(rule.id)})
    return rule_row(rule, platform.business_currency(ctx.scope))


def _switch_rule(ctx: OperationContext, data: RuleRefIn, active: bool) -> dict:
    rule = find_rule(data.id, data.rule, lock=True)
    if rule.is_active == active:
        message, code = (
            (RULE_ALREADY_ACTIVE, "pricing.rule_already_active")
            if active
            else (RULE_ALREADY_INACTIVE, "pricing.rule_already_inactive")
        )
        raise Conflict(str(message), code=code)
    if active and not _group_held(rule):
        raise Conflict(str(RULE_GROUP_DELETED), code="pricing.rule_group_deleted")
    rule.is_active = active
    rule.updated_by = _actor(ctx)
    rule.save(update_fields=["is_active", "updated_by", "updated_at"])
    record_event(ctx, events.RULE_ACTIVATED if active else events.RULE_DEACTIVATED, {"id": str(rule.id)})
    return rule_row(rule, platform.business_currency(ctx.scope))


@operation(
    "pricing.rule.deactivate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "switch off the juice deal for the rest of the year",
                "suspend the 2-for-1 juice deal for the moment",
                "stop the juice deal but keep its settings",
            ),
            "es": (
                "apaga el 2x1 de zumos hasta el año que viene",
                "suspende el 2x1 de los zumos de momento",
                "para el 2x1 de zumos, que ya lo retomaremos",
            ),
        },
        "description": "Deactivate a discount rule (by its id, code or name) so it no longer takes anything off new "
        "sales; pricing.rule.activate brings it back. Sales already made do not change.",
        "risk": "high",
    },
)
def deactivate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch_rule(ctx, data, active=False)


@operation(
    "pricing.rule.activate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="pricing.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "reactivate the summer promotion",
                "the summer discount has to come back for new sales",
                "bring the summer promotion back for this year",
            ),
            "es": (
                "reactiva la promoción de verano",
                "vuelve a aplicar el descuento de verano en las ventas nuevas",
                "recupera la promoción de verano para este año",
            ),
        },
        "description": "Bring a deactivated discount rule (by its id, code or name) back, so it applies to new sales.",
        "risk": "normal",
    },
)
def activate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch_rule(ctx, data, active=True)
