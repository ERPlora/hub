"""Input and output schemas of the pricing app's operations (OpenAPI, live params, 422 per field).

They are also the JSON Schema of the assistant's tools, so every field says what it is. Money travels
in cents (integers, never negative); a quantity is a decimal with three places in the article's own
unit (a service: units); a percent is a rate with two decimals. A price list is named by its id or, as
a person says it (assistant, voice), by its code or its name; a rule by its id, code or name; a product
by its id, SKU or name; a service by its id or name; a customer group by its id or name; a customer by
its id, name, phone or email. Every input refuses a field it does not declare. An edit changes only
the fields it sends; on a field that may be empty (the group, a day…), sending ``null`` empties it.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from apps.pricing.models import CODE_MAX_LENGTH, DEFAULT_PRIORITY, NAME_MAX_LENGTH, DiscountRule

T = TypeVar("T")

#: Ninety-nine billion in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: Tiers of one rule.
MAX_TIERS = 10
#: The largest «buy» or «free» of a rule.
MAX_UNITS = 1000

SAY_WHICH_LIST = _("Say which price list: its id, its code or its name.")
SAY_WHICH_RULE = _("Say which discount rule: its id, its code or its name.")
SAY_WHICH_ARTICLE = _("Say which product or service: its id, its name or its SKU.")
ONE_ARTICLE = _("Say one product or one service, not both.")
RANGE_BACKWARDS = _("The last day cannot be before the first one.")
CURRENCY_UNKNOWN = _("Enter a currency code of ISO 4217 with two decimals, such as EUR or USD.")
DEFAULT_HAS_GROUP = _("The general list is for everybody: take its customer group off.")
DEFAULT_CURRENCY = _("The general list goes in the business's currency (%(currency)s), the one the till sells in.")
NOT_EMPTY = _("This field cannot be empty.")
VALUE_REQUIRED = _("A rule of this type needs this value.")
VALUE_OF_ANOTHER_TYPE = _("This value belongs to another type of rule.")
TARGET_REQUIRED = _("Say which one the rule applies to.")
TARGET_OF_ANOTHER_SCOPE = _("This only goes with a rule that applies to it.")
TIERS_RISING = _("Each tier starts at a higher quantity than the one before.")
TOO_MANY_TIERS = _("At most %(count)s tiers.")

# How the Price lists screens name the data the models do not (the assistant's card names each datum by its title).
CUSTOMER_GROUP = gettext_noop("Customer group")
DISCOUNT_RULE = gettext_noop("Discount rule")

RuleType = Literal[*DiscountRule.Type.values]
RuleScope = Literal[*DiscountRule.Scope.values]
Kind = Literal["product", "service"]
#: The tax of a list's prices, as a filter: included, excluded, or as the business sells (empty).
TaxBasis = Literal["included", "excluded", "business"]
Status = Literal["active", "inactive", "all"]
Direction = Literal["asc", "desc"]


def _text(max_length: int, min_length: int = 1) -> type[str]:
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)]


def _iso_currency(value: str) -> str:
    if pycountry.currencies.get(alpha_3=value) is None or get_currency_precision(value) != 2:
        raise ValueError(str(CURRENCY_UNKNOWN))
    return value


def _upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


Code = _text(CODE_MAX_LENGTH)
Name = _text(NAME_MAX_LENGTH)
Said = _text(200)
Search = _text(120, 0)
Currency = Annotated[str, AfterValidator(_iso_currency), BeforeValidator(_upper)]
Cents = Annotated[int, Field(ge=0, le=MAX_CENTS, strict=True, json_schema_extra={"money": True})]
PositiveCents = Annotated[int, Field(gt=0, le=MAX_CENTS, strict=True, json_schema_extra={"money": True})]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=3)]
Percent = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
Units = Annotated[int, Field(ge=1, le=MAX_UNITS)]
Priority = Annotated[int, Field(ge=0, le=1_000_000)]

# Descriptions shared by several schemas.
D_LIST_ID = "The price list's id."
D_LIST = "The price list's code or name (e.g. WHOLESALE, «VIP members»), when its id is not known."
D_RULE_ID = "The discount rule's id."
D_RULE = "The discount rule's code or name (e.g. 2X1), when its id is not known."
D_CODE = "Short code, unique in the business whatever its case (e.g. VIP)."
D_NAME = "The name people see (e.g. «VIP members»)."
D_CURRENCY = "Currency of its prices, ISO 4217 with two decimals; the business's (its country's) by default."
D_TAX_INCLUDED = (
    "Whether its prices already carry the tax: true (included), false (added on top, B2B), "
    "or null to sell as the business does."
)
D_GROUP_ID = "Id of the customer group whose members get it; null for nobody's group."
D_GROUP = "Name of the customer group (e.g. VIP), when its id is not known."
D_FROM = "First day it applies (YYYY-MM-DD, included); null = since always."
D_UNTIL = "Last day it applies (YYYY-MM-DD, included); null = with no end."
D_DEFAULT = "Whether it is the general list, for every customer (only one is; it has no group)."
D_PRODUCT_ID = "The product's id (Inventory)."
D_PRODUCT = "The product's SKU or name, when its id is not known."
D_SERVICE_ID = "The service's id (Services)."
D_SERVICE = "The service's name, when its id is not known."
D_PRICE = "Price in cents of the list's currency (12.50 = 1250), for the same quantity the catalog's price is for."
D_MIN_QUANTITY = "From this quantity on (in the product's unit; a service: units); 1 by default."
D_SEARCH = "Free text to search."
D_DIR = "Sort direction: asc or desc."
D_STATUS = "Which ones: active (default), inactive or all."


def _named(value: str | None, info: ValidationInfo, id_field: str, message) -> str | None:
    """The text reference is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(message))
    return value


def _one_article(value: str | None, info: ValidationInfo) -> str | None:
    """Declared last: a product (id or text) or a service (id or text), exactly one of the two."""
    service = info.data.get("service_id") is not None or info.data.get("service") is not None
    product = value is not None or info.data.get("product_id") is not None
    if not ({"service_id", "service", "product_id"} <= set(info.data)):
        return value  # another field already failed: that error is the one to say
    if product and service:
        raise ValueError(str(ONE_ARTICLE))
    if not product and not service:
        raise ValueError(str(SAY_WHICH_ARTICLE))
    return value


def _not_empty(value: Any) -> Any:
    if value is None:
        raise ValueError(str(NOT_EMPTY))
    return value


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


# Pages: every list is paginated, limit ≤ 100.


class PageIn(In):
    limit: int = Field(50, ge=1, le=100, description="How many rows to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many rows to skip, to read the next pages.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="How many rows match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The rows skipped before this page.")


class DeletedOut(Schema):
    id: UUID = Field(description="The id of what was removed.")


# Price lists


class PriceListListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Code or name.")
    code: Search | None = Field(None, description="Part of the code.")
    name: Search | None = Field(None, description="Part of the name.")
    currency: Search | None = Field(None, description="Part of the currency code.")
    customer_group_id: UUID | None = Field(None, description="Only the lists of this customer group.")
    tax_basis: TaxBasis | None = Field(
        None, description="Only the lists whose prices carry the tax (included), not (excluded), or as the business."
    )
    status: Status = Field("active", description=D_STATUS)
    sort: Literal["code", "name", "currency", "customer_group_name", "tax_included"] = Field(
        "name", description="The column to order by; the code and the id break ties."
    )
    dir: Direction = Field("asc", description=D_DIR)


class PriceListRefIn(In):
    id: UUID | None = Field(None, description=D_LIST_ID)
    price_list: Said | None = Field(None, validate_default=True, description=D_LIST)

    @field_validator("price_list")
    @classmethod
    def _list_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "id", SAY_WHICH_LIST)


class _ListFields(In):
    @field_validator("valid_until", check_fields=False)
    @classmethod
    def _in_order(cls, until: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("valid_from")
        if until is not None and start is not None and until < start:
            raise ValueError(str(RANGE_BACKWARDS))
        return until


class PriceListIn(_ListFields):
    code: Code = Field(description=D_CODE)
    name: Name = Field(description=D_NAME)
    currency: Currency | None = Field(None, description=D_CURRENCY)
    tax_included: bool | None = Field(None, description=D_TAX_INCLUDED)
    customer_group_id: UUID | None = Field(None, description=D_GROUP_ID)
    customer_group: Said | None = Field(None, title=CUSTOMER_GROUP, description=D_GROUP)
    valid_from: dt.date | None = Field(None, description=D_FROM)
    valid_until: dt.date | None = Field(None, description=D_UNTIL)
    is_default: bool = Field(False, description=D_DEFAULT)

    @field_validator("is_default")
    @classmethod
    def _general_for_everybody(cls, value: bool, info: ValidationInfo) -> bool:
        # Its currency is the business's, which only the operation knows (services.create_price_list).
        if value and (info.data.get("customer_group_id") or info.data.get("customer_group")):
            raise ValueError(str(DEFAULT_HAS_GROUP))
        return value


class PriceListPatchIn(PriceListRefIn, _ListFields):
    """Changes only the fields sent; ``null`` empties the group, the tax basis or a day."""

    code: Code | None = Field(None, description=D_CODE)
    name: Name | None = Field(None, description=D_NAME)
    currency: Currency | None = Field(None, description=D_CURRENCY)
    tax_included: bool | None = Field(None, description=D_TAX_INCLUDED)
    customer_group_id: UUID | None = Field(None, description=D_GROUP_ID)
    customer_group: Said | None = Field(None, title=CUSTOMER_GROUP, description=D_GROUP)
    valid_from: dt.date | None = Field(None, description=D_FROM)
    valid_until: dt.date | None = Field(None, description=D_UNTIL)

    _required = field_validator("code", "name", "currency")(classmethod(lambda cls, value: _not_empty(value)))


class PriceListDefaultIn(PriceListRefIn):
    is_default: bool = Field(True, description="true makes it the general list; false takes the mark off it.")


class PriceListOut(Schema):
    id: UUID = Field(description=D_LIST_ID)
    code: str = Field(description=D_CODE)
    name: str = Field(description=D_NAME)
    currency: str = Field(description=D_CURRENCY)
    tax_included: bool | None = Field(description=D_TAX_INCLUDED)
    customer_group_id: UUID | None = Field(description=D_GROUP_ID)
    customer_group_name: str | None = Field(description="The group's name; null without group or if it was deleted.")
    valid_from: dt.date | None = Field(description=D_FROM)
    valid_until: dt.date | None = Field(description=D_UNTIL)
    is_default: bool = Field(description=D_DEFAULT)
    is_active: bool = Field(description="Whether it applies to new sales.")
    item_count: int = Field(description="How many prices it has.")
    updated_at: dt.datetime = Field(description="Its last change.")


# Prices


class PriceItemListIn(PageIn):
    price_list_id: UUID | None = Field(None, description="Only the prices of this list. " + D_LIST_ID)
    price_list: Said | None = Field(None, description="Only the prices of this list. " + D_LIST)
    product_id: UUID | None = Field(None, description="Only this product's prices, in every list.")
    service_id: UUID | None = Field(None, description="Only this service's prices, in every list.")
    kind: Kind | None = Field(None, description="Only products or only services.")
    search: Search | None = Field(None, description=D_SEARCH + " Product name or SKU, or service name.")
    sort: Literal["name", "min_quantity", "price"] = Field(
        "name", description="The column to order by; the from quantity and the id break ties."
    )
    dir: Direction = Field("asc", description=D_DIR)


class _ArticleFields(In):
    """A product (by id, SKU or name) or a service (by id or name): exactly one."""

    service_id: UUID | None = Field(None, description=D_SERVICE_ID)
    service: Said | None = Field(None, description=D_SERVICE)
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID)
    product: Said | None = Field(None, validate_default=True, description=D_PRODUCT)

    @field_validator("product")
    @classmethod
    def _one_article(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _one_article(value, info)


class PriceItemIn(_ArticleFields):
    price_list_id: UUID | None = Field(None, description=D_LIST_ID)
    price_list: Said | None = Field(None, validate_default=True, description=D_LIST)
    price: Cents = Field(description=D_PRICE)
    min_quantity: Quantity = Field(Decimal("1"), description=D_MIN_QUANTITY)

    @field_validator("price_list")
    @classmethod
    def _list_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "price_list_id", SAY_WHICH_LIST)


class PriceItemPatchIn(In):
    """Changes only the fields sent."""

    id: UUID = Field(description="The price's id.")
    price: Cents | None = Field(None, description=D_PRICE)
    min_quantity: Quantity | None = Field(None, description=D_MIN_QUANTITY)

    _required = field_validator("price", "min_quantity")(classmethod(lambda cls, value: _not_empty(value)))


class PriceItemRefIn(In):
    """A price by its id, or by its list, its article and its from quantity (1 if not said)."""

    id: UUID | None = Field(None, description="The price's id.")
    price_list_id: UUID | None = Field(None, description=D_LIST_ID)
    price_list: Said | None = Field(None, validate_default=True, description=D_LIST)
    service_id: UUID | None = Field(None, description=D_SERVICE_ID)
    service: Said | None = Field(None, description=D_SERVICE)
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID)
    product: Said | None = Field(None, validate_default=True, description=D_PRODUCT)
    min_quantity: Quantity = Field(Decimal("1"), description=D_MIN_QUANTITY)

    @field_validator("price_list")
    @classmethod
    def _list_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("id") is not None:
            return value
        return _named(value, info, "price_list_id", SAY_WHICH_LIST)

    @field_validator("product")
    @classmethod
    def _article_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("id") is not None:
            return value
        return _one_article(value, info)


class PriceItemOut(Schema):
    id: UUID = Field(description="The price's id.")
    price_list_id: UUID = Field(description=D_LIST_ID)
    price_list_code: str = Field(description="The list's code.")
    price_list_name: str = Field(description="The list's name.")
    kind: Kind = Field(description="product or service.")
    product_id: UUID | None = Field(description=D_PRODUCT_ID)
    service_id: UUID | None = Field(description=D_SERVICE_ID)
    name: str = Field(description="The article's name.")
    sku: str | None = Field(description="The product's SKU; null for a service.")
    unit: str | None = Field(description="The product's unit (ud, kg…); null for a service.")
    base_price: int | None = Field(description="The catalog's price in cents (Inventory); null for a service.")
    min_quantity: Decimal = Field(description=D_MIN_QUANTITY)
    price: int = Field(description=D_PRICE)
    updated_at: dt.datetime = Field(description="Its last change.")


# Rules


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
    id: UUID | None = Field(None, description=D_RULE_ID)
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
    category_id: UUID | None = Field(None, description="category: the category's id (Inventory).")
    category: Said | None = Field(None, description="category: the category's name, when its id is not known.")
    product_id: UUID | None = Field(None, description="product: " + D_PRODUCT_ID)
    product: Said | None = Field(None, description="product: " + D_PRODUCT)
    service_id: UUID | None = Field(None, description="service: " + D_SERVICE_ID)
    service: Said | None = Field(None, description="service: " + D_SERVICE)
    customer_group_id: UUID | None = Field(None, description="Only for the members of this group. " + D_GROUP_ID)
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
    category_id: UUID | None = Field(None, description="category: the category's id (Inventory).")
    category: Said | None = Field(None, description="category: the category's name, when its id is not known.")
    product_id: UUID | None = Field(None, description="product: " + D_PRODUCT_ID)
    product: Said | None = Field(None, description="product: " + D_PRODUCT)
    service_id: UUID | None = Field(None, description="service: " + D_SERVICE_ID)
    service: Said | None = Field(None, description="service: " + D_SERVICE)
    customer_group_id: UUID | None = Field(None, description="Only for the members of this group. " + D_GROUP_ID)
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


def rule_problems(values: dict[str, Any]) -> dict[str, str]:
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
    amount: int | None = Field(description="fixed: cents taken off each unit of the price sold (each kg of an article priced per kg).")
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


# The price of a line


class ResolveIn(_ArticleFields):
    customer_id: UUID | None = Field(None, description="The customer's id (Customers); none for a sale without customer.")
    customer: Said | None = Field(None, description="The customer's name, phone or email, when the id is not known.")
    quantity: Quantity = Field(Decimal("1"), description="The quantity of the line, in the article's unit; 1 by default.")
    tax_included: bool = Field(
        True,
        description="Whether the sale's prices carry the tax (true by default, as a till's do): only the lists "
        "of that basis, or that follow the business, compete; prices of different bases are never compared.",
    )
    when: AwareDatetime | None = Field(
        None, description="The moment of the sale, with its time zone; now by default. Its day decides the dates."
    )
    price_list_id: UUID | None = Field(None, description="Only this price list. " + D_LIST_ID)
    price_list: Said | None = Field(None, description="Only this price list. " + D_LIST)


class ResolveOut(Schema):
    kind: Kind = Field(description="product or service.")
    product_id: UUID | None = Field(description=D_PRODUCT_ID)
    service_id: UUID | None = Field(description=D_SERVICE_ID)
    name: str = Field(description="The article's name.")
    quantity: Decimal = Field(description="The quantity of the line.")
    date: dt.date = Field(description="The business day the dates were read on.")
    base_price: int = Field(description="The catalog's price in cents.")
    unit_price: int = Field(description="The price the line takes, in cents: the list's, or the catalog's.")
    price_list_id: UUID | None = Field(description="The list the price comes from; null = the catalog's.")
    price_list_code: str | None = Field(description="That list's code.")
    price_list_name: str | None = Field(description="That list's name.")
    tax_included: bool | None = Field(description="Whether that list's prices carry the tax; null = as the business sells.")
    currency: str = Field(description="The currency of the price.")
    line_amount: int = Field(description="Price × quantity (in the unit of the price), in cents, half up.")
    discount: int = Field(description="Cents the rule takes off the line; 0 without rule.")
    rule_id: UUID | None = Field(description="The rule that gives the discount; null = none.")
    rule_code: str | None = Field(description="That rule's code.")
    rule_name: str | None = Field(description="That rule's name.")
    rule_type: RuleType | None = Field(description="That rule's type.")
    total: int = Field(description="The line after the discount, in cents.")


# Reactions to other apps' events


class CatalogEventIn(Schema):
    """The payload of ``inventory.product.deleted``, ``inventory.category.deleted``,
    ``customer.group.deleted`` or ``service.service.updated``: only its id is read."""

    model_config = ConfigDict(extra="ignore")

    id: UUID = Field(description="The id of the product, category, group or service of the event.")


class CatalogOut(Schema):
    lists: int = Field(description="Price lists changed.")
    items: int = Field(description="Prices removed or changed.")
    rules: int = Field(description="Rules switched off or changed.")
