"""Schemas of the price of a line (``pricing.price.resolve``)."""

import datetime as dt
from decimal import Decimal
from uuid import UUID

from ninja import Field, Schema
from pydantic import AwareDatetime

from apps.pricing.schemas.fields import (
    D_LIST,
    D_LIST_ID,
    D_PRODUCT_ID,
    D_SERVICE_ID,
    Kind,
    Quantity,
    RuleType,
    Said,
    _ArticleFields,
)


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
    base_price: int = Field(description="The catalog's price in cents.", json_schema_extra={"money": True})
    unit_price: int = Field(
        description="The price the line takes, in cents: the list's, or the catalog's.",
        json_schema_extra={"money": True},
    )
    price_list_id: UUID | None = Field(description="The list the price comes from; null = the catalog's.")
    price_list_code: str | None = Field(description="That list's code.")
    price_list_name: str | None = Field(description="That list's name.")
    tax_included: bool | None = Field(description="Whether that list's prices carry the tax; null = as the business sells.")
    currency: str = Field(description="The currency of the price.")
    line_amount: int = Field(
        description="Price × quantity (in the unit of the price), in cents, half up.",
        json_schema_extra={"money": True},
    )
    discount: int = Field(
        description="Cents the rule takes off the line; 0 without rule.",
        json_schema_extra={"money": True},
    )
    rule_id: UUID | None = Field(description="The rule that gives the discount; null = none.")
    rule_code: str | None = Field(description="That rule's code.")
    rule_name: str | None = Field(description="That rule's name.")
    rule_type: RuleType | None = Field(description="That rule's type.")
    total: int = Field(description="The line after the discount, in cents.", json_schema_extra={"money": True})
