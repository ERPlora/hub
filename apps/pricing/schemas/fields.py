"""What the schemas of the pricing app share: the types and limits of their fields, the messages, titles and record
marks of several topics, the descriptions they repeat, pages, the closed input and naming one article."""

from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

import pycountry
from babel.numbers import get_currency_precision
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, BeforeValidator, ConfigDict, StringConstraints, ValidationInfo, field_validator

from apps.pricing.models import CODE_MAX_LENGTH, NAME_MAX_LENGTH, DiscountRule
from base.schemas.assistant import names

T = TypeVar("T")

#: Ninety-nine billion in cents: far above any price, inside a bigint.
MAX_CENTS = 9_999_999_999_999
#: The largest «buy» or «free» of a rule.
MAX_UNITS = 1000

SAY_WHICH_LIST = _("Say which price list: its id, its code or its name.")
SAY_WHICH_ARTICLE = _("Say which product or service: its id, its name or its SKU.")
ONE_ARTICLE = _("Say one product or one service, not both.")
RANGE_BACKWARDS = _("The last day cannot be before the first one.")
CURRENCY_UNKNOWN = _("Enter a currency code of ISO 4217 with two decimals, such as EUR or USD.")
NOT_EMPTY = _("This field cannot be empty.")

# How the Price lists screens name the data the models do not (the assistant's card names each datum by its title).
CUSTOMER_GROUP = gettext_noop("Customer group")
DISCOUNT_RULE = gettext_noop("Discount rule")
PRICE_LIST = gettext_noop("Price list")
PRICE = gettext_noop("Price")

# The assistant's card names the record a write acts on by these reads (base/assistant/cards.py ``REFERS``), run as whoever
# asks, never by its id: a list and a rule by their name, as the Price lists screen; a price by its article and its
# list, as its dialogs; a product by Inventory's read; a category, a customer group or a service (Services is no
# requirement) by the read of what a price or a rule points at in another app. Whoever changes prices reads them all.
A_LIST = names("pricing.price_list.get")
A_PRICE = names("pricing.price_item.get", name=("label",))
A_RULE = names("pricing.rule.get")
A_PRODUCT = names("inventory.product.get")
A_SERVICE = names("pricing.catalog.get", by="service_id")
A_CATEGORY = names("pricing.catalog.get", by="category_id")
A_GROUP = names("pricing.catalog.get", by="customer_group_id")

RuleType = Literal[*DiscountRule.Type.values]
Kind = Literal["product", "service"]
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
D_CODE = "Short code, unique in the business whatever its case (e.g. VIP)."
D_NAME = "The name people see (e.g. «VIP members»)."
D_GROUP_ID = "Id of the customer group whose members get it; null for nobody's group."
D_GROUP = "Name of the customer group (e.g. VIP), when its id is not known."
D_FROM = "First day it applies (YYYY-MM-DD, included); null = since always."
D_UNTIL = "Last day it applies (YYYY-MM-DD, included); null = with no end."
D_PRODUCT_ID = "The product's id (Inventory)."
D_PRODUCT = "The product's SKU or name, when its id is not known."
D_SERVICE_ID = "The service's id (Services)."
D_SERVICE = "The service's name, when its id is not known."
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


class _ArticleFields(In):
    """A product (by id, SKU or name) or a service (by id or name): exactly one."""

    service_id: UUID | None = Field(None, description=D_SERVICE_ID, json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description=D_SERVICE)
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID, json_schema_extra=A_PRODUCT)
    product: Said | None = Field(None, validate_default=True, description=D_PRODUCT)

    @field_validator("product")
    @classmethod
    def _one_article(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _one_article(value, info)
