"""Schemas of the prices of a list (``pricing.price_item.*``)."""

import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.pricing.schemas.fields import (
    A_LIST,
    A_PRICE,
    A_PRODUCT,
    A_SERVICE,
    D_DIR,
    D_LIST,
    D_LIST_ID,
    D_PRODUCT,
    D_PRODUCT_ID,
    D_SEARCH,
    D_SERVICE,
    D_SERVICE_ID,
    PRICE,
    SAY_WHICH_LIST,
    Cents,
    Direction,
    In,
    Kind,
    PageIn,
    Quantity,
    Said,
    Search,
    _ArticleFields,
    _named,
    _not_empty,
    _one_article,
)
from base.schemas.assistant import in_currency_of

D_PRICE = "Price in cents of the list's currency (12.50 = 1250), for the same quantity the catalog's price is for."
D_MIN_QUANTITY = "From this quantity on (in the product's unit; a service: units); 1 by default."


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


class PriceItemIn(_ArticleFields):
    price_list_id: UUID | None = Field(
        None, description=D_LIST_ID, json_schema_extra={**in_currency_of("pricing.price_list.get"), **A_LIST}
    )
    price_list: Said | None = Field(
        None, validate_default=True, description=D_LIST, json_schema_extra=in_currency_of("pricing.price_list.get", by="price_list")
    )
    price: Cents = Field(description=D_PRICE)
    min_quantity: Quantity = Field(Decimal("1"), description=D_MIN_QUANTITY)

    @field_validator("price_list")
    @classmethod
    def _list_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "price_list_id", SAY_WHICH_LIST)


class PriceItemPatchIn(In):
    """Changes only the fields sent."""

    id: UUID = Field(
        title=PRICE, description="The price's id.", json_schema_extra={**in_currency_of("pricing.price_item.get"), **A_PRICE}
    )
    price: Cents | None = Field(None, description=D_PRICE)
    min_quantity: Quantity | None = Field(None, description=D_MIN_QUANTITY)

    _required = field_validator("price", "min_quantity")(classmethod(lambda cls, value: _not_empty(value)))


class PriceItemIdIn(In):
    id: UUID = Field(description="The price's id.")


class PriceItemRefIn(In):
    """A price by its id, or by its list, its article and its from quantity (1 if not said)."""

    id: UUID | None = Field(None, title=PRICE, description="The price's id.", json_schema_extra=A_PRICE)
    price_list_id: UUID | None = Field(None, description=D_LIST_ID, json_schema_extra=A_LIST)
    price_list: Said | None = Field(None, validate_default=True, description=D_LIST)
    service_id: UUID | None = Field(None, description=D_SERVICE_ID, json_schema_extra=A_SERVICE)
    service: Said | None = Field(None, description=D_SERVICE)
    product_id: UUID | None = Field(None, description=D_PRODUCT_ID, json_schema_extra=A_PRODUCT)
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
    base_price: int | None = Field(
        description="The catalog's price in cents (Inventory); null for a service.",
        json_schema_extra={"money": True},
    )
    min_quantity: Decimal = Field(description=D_MIN_QUANTITY)
    price: int = Field(description=D_PRICE, json_schema_extra={"money": True})
    currency: str = Field(description="The currency of its list, the one its price is in (ISO 4217).")
    updated_at: dt.datetime = Field(description="Its last change.")


class PriceItemDetailOut(PriceItemOut):
    """One price as the list shows it, and how it is named outside its list."""

    label: str = Field(
        description="How it is named outside its list, in the reader's language: its article, its list and, from a "
        "quantity on, that quantity (e.g. «Shampoo · VIP prices · from 10»)."
    )
