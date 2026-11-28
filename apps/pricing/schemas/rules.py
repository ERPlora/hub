"""Schemas of the discount rules (``pricing.rule.*``) and what makes a rule coherent (``rule_problems``)."""

import datetime as dt
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.pricing.models import DEFAULT_PRIORITY, DiscountRule
from apps.pricing.schemas.fields import (
    A_CATEGORY,
    A_GROUP,
    A_PRODUCT,
    A_RULE,
    A_SERVICE,
    CUSTOMER_GROUP,
    D_CODE,
    D_DIR,
    D_FROM,
    D_GROUP,
    D_GROUP_ID,
    D_NAME,
    D_PRODUCT,
    D_PRODUCT_ID,
    D_SEARCH,
    D_SERVICE,
    D_SERVICE_ID,
    D_STATUS,
    D_UNTIL,
    DISCOUNT_RULE,
    RANGE_BACKWARDS,
    Code,
    Direction,
    In,
    Name,
    PageIn,
    Percent,
    PositiveCents,
    Priority,
    Quantity,
    RuleType,
    Said,
    Search,
    Status,
    Units,
    _named,
    _not_empty,
)

#: Tiers of one rule.
MAX_TIERS = 10

SAY_WHICH_RULE = _("Say which discount rule: its id, its code or its name.")
VALUE_REQUIRED = _("A rule of this type needs this value.")
VALUE_OF_ANOTHER_TYPE = _("This value belongs to another type of rule.")
TARGET_REQUIRED = _("Say which one the rule applies to.")
TARGET_OF_ANOTHER_SCOPE = _("This only goes with a rule that applies to it.")
TIERS_RISING = _("Each tier starts at a higher quantity than the one before.")
TOO_MANY_TIERS = _("At most %(count)s tiers.")

RuleScope = Literal[*DiscountRule.Scope.values]

D_RULE_ID = "The discount rule's id."
D_RULE = "The discount rule's code or name (e.g. 2X1), when its id is not known."


class Tier(In):
    min_quantity: Quantity = Field(description="From this quantity on.")
    percent: Percent = Field(description="The percent taken off the line, up to 100 with two decimals.")


class RuleListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Code or name.")
    code: Search | None = Field(None, description="Part of the code.")
    name: Search | None = Field(None, description="Part of the name.")
    rule_type: RuleType | None = Field(None, description="Only rules of this type.")
    applies_to: RuleScope | None = Field(None, description="Only rules of this scope.")
    customer_group_id: UUID | None = Field(None, description="Only the rules of this customer group.")
    status: Status = Field("active", description=D_STATUS)
    sort: Literal["code", "name", "rule_type", "priority"] = Field(
        "name", description="The column to order by; the code and the id break ties."
    )
    dir: Direction = Field("asc", description=D_DIR)


class RuleRefIn(In):
    id: UUID | None = Field(None, title=DISCOUNT_RULE, description=D_RULE_ID, json_schema_extra=A_RULE)
    rule: Said | None = Field(None, validate_default=True, title=DISCOUNT_RULE, description=D_RULE)

    @field_validator("rule")
    @classmethod
    def _rule_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "id", SAY_WHICH_RULE)


D_RULE_TYPE = (
    "percent (a percent off the line), fixed (an amount off each unit sold), buy_x_get_y (of every "
    "buy + free units, the free ones cost nothing) or tiered (a percent by quantity tiers)."
)
D_SCOPE = (
    "What it applies to: all, products, services, category (one of Inventory), product (one) or "
    "service (one)."
)


class RuleIn(In):
    code: Code = Field(description=D_CODE)
    name: Name = Field(description=D_NAME)
    rule_type: RuleType = Field(description=D_RULE_TYPE)
    percent: Percent | None = Field(None, description="percent: the percent taken off the line, up to 100.")
    amount: PositiveCents | None = Field(None, description="fixed: cents taken off each unit of the price sold (each kg of an article priced per kg).")
    buy_quantity: Units | None = Field(None, description="buy_x_get_y: the units of the price that are paid (the X).")
    get_quantity: Units | None = Field(None, description="buy_x_get_y: the units of the price that are free (the Y), rounded down.")
    tiers: list[Tier] = Field(
        default_factory=list,
        max_length=MAX_TIERS,
        description="tiered: up to 10 tiers by rising quantity (in the unit of the price), each with the percent from it on.",
    )
    applies_to: RuleScope = Field("all", description=D_SCOPE)
    category_id: UUID | None = Field(
        None, description="category: the category's id (Inventory).", json_schema_extra=A_CATEGORY
    )
    category: Said | None = Field(None, description="category: the category's name, when its id is not known.")
    product_id: UUID | None = Field(None, description="product: " + D_PRODUCT_ID, json_schema_extra=A_PRODUCT)
    product: Said | None = Field(None, description="product: " + D_PRODUCT)
    service_id: UUID | None = Field(None, description="service: " + D_SERVICE_ID, json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description="service: " + D_SERVICE)
    customer_group_id: UUID | None = Field(
        None, description="Only for the members of this group. " + D_GROUP_ID, json_schema_extra=A_GROUP
    )
    customer_group: Said | None = Field(None, title=CUSTOMER_GROUP, description="Only for the members of this group. " + D_GROUP)
    min_quantity: Quantity | None = Field(None, description="Only from this quantity of the line on, in the unit of its price (kg of an article priced per kg).")
    valid_from: dt.date | None = Field(None, description=D_FROM)
    valid_until: dt.date | None = Field(None, description=D_UNTIL)
    priority: Priority = Field(DEFAULT_PRIORITY, description="With equal discounts, the lower number wins; 100 by default.")


class RulePatchIn(RuleRefIn):
    """Changes only the fields sent; ``null`` empties the group, the minimum quantity or a day."""

    code: Code | None = Field(None, description=D_CODE)
    name: Name | None = Field(None, description=D_NAME)
    rule_type: RuleType | None = Field(None, description=D_RULE_TYPE)
    percent: Percent | None = Field(None, description="percent: the percent taken off the line, up to 100.")
    amount: PositiveCents | None = Field(None, description="fixed: cents taken off each unit of the price sold (each kg of an article priced per kg).")
    buy_quantity: Units | None = Field(None, description="buy_x_get_y: the units of the price that are paid (the X).")
    get_quantity: Units | None = Field(None, description="buy_x_get_y: the units of the price that are free (the Y), rounded down.")
    tiers: list[Tier] | None = Field(None, max_length=MAX_TIERS, description="tiered: up to 10 tiers by rising quantity.")
    applies_to: RuleScope | None = Field(None, description=D_SCOPE)
    category_id: UUID | None = Field(
        None, description="category: the category's id (Inventory).", json_schema_extra=A_CATEGORY
    )
    category: Said | None = Field(None, description="category: the category's name, when its id is not known.")
    product_id: UUID | None = Field(None, description="product: " + D_PRODUCT_ID, json_schema_extra=A_PRODUCT)
    product: Said | None = Field(None, description="product: " + D_PRODUCT)
    service_id: UUID | None = Field(None, description="service: " + D_SERVICE_ID, json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description="service: " + D_SERVICE)
    customer_group_id: UUID | None = Field(
        None, description="Only for the members of this group. " + D_GROUP_ID, json_schema_extra=A_GROUP
    )
    customer_group: Said | None = Field(None, title=CUSTOMER_GROUP, description="Only for the members of this group. " + D_GROUP)
    min_quantity: Quantity | None = Field(None, description="Only from this quantity of the line on, in the unit of its price (kg of an article priced per kg).")
    valid_from: dt.date | None = Field(None, description=D_FROM)
    valid_until: dt.date | None = Field(None, description=D_UNTIL)
    priority: Priority | None = Field(None, description="With equal discounts, the lower number wins.")

    _required = field_validator("code", "name", "rule_type", "applies_to", "priority", "tiers")(
        classmethod(lambda cls, value: _not_empty(value))
    )


#: The value(s) each type of rule carries; the others stay empty.
TYPE_VALUES: dict[str, tuple[str, ...]] = {
    "percent": ("percent",),
    "fixed": ("amount",),
    "buy_x_get_y": ("buy_quantity", "get_quantity"),
    "tiered": ("tiers",),
}
#: The target each scope names: (field of the error, id key, text key).
SCOPE_TARGETS: dict[str, tuple[str, str, str]] = {
    "category": ("category", "category_id", "category"),
    "product": ("product", "product_id", "product"),
    "service": ("service", "service_id", "service"),
}


def _given(value: Any) -> bool:
    return value not in (None, [], "")


def rule_problems(values: dict[str, Any]) -> dict[str, str]:  # noqa: C901
    """What is wrong in a rule as it would be saved (``{field: message}``; empty = coherent).

    Each type wants its value and nothing of another type's; each scope its target and no other one;
    tiers rise; the days are in order. Pure: the service calls it with the stored row merged with what
    an edit sends, so a create and an edit say the same.
    """
    problems: dict[str, str] = {}
    rule_type = values.get("rule_type")
    for name in TYPE_VALUES.get(rule_type, ()):
        if not _given(values.get(name)):
            problems[name] = str(VALUE_REQUIRED)
    for other, names in TYPE_VALUES.items():
        if other == rule_type:
            continue
        for name in names:
            if _given(values.get(name)):
                problems[name] = str(VALUE_OF_ANOTHER_TYPE)
    tiers = values.get("tiers") or []
    if rule_type == "tiered" and tiers:
        quantities = [Decimal(tier["min_quantity"]) for tier in tiers]
        if any(later <= earlier for earlier, later in zip(quantities, quantities[1:], strict=False)):
            problems["tiers"] = str(TIERS_RISING)
    scope = values.get("applies_to")
    for target_scope, (field, id_key, text_key) in SCOPE_TARGETS.items():
        given = _given(values.get(id_key)) or _given(values.get(text_key))
        if target_scope == scope and not given:
            problems[field] = str(TARGET_REQUIRED)
        elif target_scope != scope and given:
            problems[field] = str(TARGET_OF_ANOTHER_SCOPE)
    start, until = values.get("valid_from"), values.get("valid_until")
    if start is not None and until is not None and until < start:
        problems["valid_until"] = str(RANGE_BACKWARDS)
    return problems


class TierOut(Schema):
    min_quantity: Decimal = Field(description="From this quantity on.")
    percent: Decimal = Field(description="The percent taken off the line.")


class RuleOut(Schema):
    id: UUID = Field(description=D_RULE_ID)
    code: str = Field(description=D_CODE)
    name: str = Field(description=D_NAME)
    rule_type: RuleType = Field(description=D_RULE_TYPE)
    percent: Decimal | None = Field(description="percent: the percent taken off the line.")
    amount: int | None = Field(
        description="fixed: cents taken off each unit of the price sold (each kg of an article priced per kg).",
        json_schema_extra={"money": True},
    )
    currency: str = Field(
        description="The currency its amount per unit is in (ISO 4217): the business's, as a rule belongs to no list."
    )
    buy_quantity: int | None = Field(description="buy_x_get_y: the units that are paid.")
    get_quantity: int | None = Field(description="buy_x_get_y: the units that are free.")
    tiers: list[TierOut] = Field(description="tiered: the tiers by rising quantity.")
    applies_to: RuleScope = Field(description=D_SCOPE)
    category_id: UUID | None = Field(description="The category's id.")
    category_name: str | None = Field(description="The category's name.")
    product_id: UUID | None = Field(description=D_PRODUCT_ID)
    product_name: str | None = Field(description="The product's name.")
    service_id: UUID | None = Field(description=D_SERVICE_ID)
    service_name: str | None = Field(description="The service's name.")
    target_deleted: bool = Field(
        description="Inventory deleted its category or product: the rule no longer applies to anything."
    )
    customer_group_id: UUID | None = Field(description=D_GROUP_ID)
    customer_group_name: str | None = Field(description="The group's name; null without group or if it was deleted.")
    min_quantity: Decimal | None = Field(description="Only from this quantity of the line on, in the unit of its price (kg of an article priced per kg).")
    valid_from: dt.date | None = Field(description=D_FROM)
    valid_until: dt.date | None = Field(description=D_UNTIL)
    priority: int = Field(description="With equal discounts, the lower number wins.")
    is_active: bool = Field(description="Whether it applies to new sales.")
    updated_at: dt.datetime = Field(description="Its last change.")


class RuleDeletedOut(Schema):
    id: UUID = Field(description=D_RULE_ID)
    code: str = Field(description="The code it had, free now for a new discount rule.")
