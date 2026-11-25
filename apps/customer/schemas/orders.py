"""Schemas of a customer on an open order of Sales: linking them and reading the link."""

from datetime import datetime
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.customer.schemas.fields import A_CUSTOMER, A_CUSTOMER_SAID, A_ORDER, CustomerOfIn, Page, PageIn, Reference
from base.schemas.assistant import unless_given


class OrderLinkIn(Schema):
    order_id: UUID = Field(
        title=gettext_noop("Open order"), description="The open order's id in the sale app.", json_schema_extra=A_ORDER
    )
    customer_id: UUID | None = Field(
        None, description="The customer's id; without a customer the link is removed.", json_schema_extra=A_CUSTOMER
    )
    customer: Reference | None = Field(
        None,
        description="The customer's name (or a part of it), phone or email.",
        json_schema_extra=unless_given(A_CUSTOMER_SAID, "customer_id"),
    )


class OrderIn(Schema):
    order_id: UUID = Field(description="The order's id in the sale app.")


class OrderListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=60, description="A piece of the order's id."
    )


class OrderNamedOut(Schema):
    order_id: UUID = Field(description="The order's id.")
    name: str = Field(description="The order as Sales names it: its title or, with none, its amount.")


class OrderCustomerOut(Schema):
    order_id: UUID = Field(description="The order's id.")
    customer_id: UUID | None = Field(
        description="Its customer; empty when it has none."
    )


class OrderRow(Schema):
    order_id: UUID = Field(description="The order's id.")
    customer_id: UUID = Field(description="The customer's id.")
    linked_at: datetime = Field(description="When the customer was put on the order.")


OrderPage = Page[OrderRow]
