"""Schemas of the price lists (``pricing.price_list.*``)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.pricing.schemas.fields import (
    A_GROUP,
    A_LIST,
    CUSTOMER_GROUP,
    D_CODE,
    D_DIR,
    D_FROM,
    D_GROUP,
    D_GROUP_ID,
    D_LIST,
    D_LIST_ID,
    D_NAME,
    D_SEARCH,
    D_STATUS,
    D_UNTIL,
    PRICE_LIST,
    RANGE_BACKWARDS,
    SAY_WHICH_LIST,
    Code,
    Currency,
    Direction,
    In,
    Name,
    PageIn,
    Said,
    Search,
    Status,
    _named,
    _not_empty,
)

DEFAULT_HAS_GROUP = _("The general list is for everybody: take its customer group off.")
DEFAULT_CURRENCY = _("The general list goes in the business's currency (%(currency)s), the one the till sells in.")

#: The tax of a list's prices, as a filter: included, excluded, or as the business sells (empty).
TaxBasis = Literal["included", "excluded", "business"]

D_CURRENCY = "Currency of its prices, ISO 4217 with two decimals; the business's (its country's) by default."
D_TAX_INCLUDED = (
    "Whether its prices already carry the tax: true (included), false (added on top, B2B), "
    "or null to sell as the business does."
)
D_DEFAULT = "Whether it is the general list, for every customer (only one is; it has no group)."


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
    id: UUID | None = Field(None, title=PRICE_LIST, description=D_LIST_ID, json_schema_extra=A_LIST)
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
    customer_group_id: UUID | None = Field(None, description=D_GROUP_ID, json_schema_extra=A_GROUP)
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
    customer_group_id: UUID | None = Field(None, description=D_GROUP_ID, json_schema_extra=A_GROUP)
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


class PriceListDeletedOut(Schema):
    id: UUID = Field(description=D_LIST_ID)
    code: str = Field(description="The code it had, free now for a new price list.")
