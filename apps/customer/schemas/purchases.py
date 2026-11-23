"""Schemas of a customer's purchases: the sales recorded on the card, their refunds and voids, and the cards whose
totals disagree with their history."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from ninja import Field, Schema

from apps.customer.models import Purchase
from apps.customer.schemas.fields import INT8_MAX, CustomerOfIn, Page, PageIn, _decimals, _text

PurchaseSort = Literal["recorded_at", "amount", "status"]


class PurchaseListIn(CustomerOfIn, PageIn):
    search: str | None = Field(
        None, max_length=60, description="A piece of the sale's id."
    )
    status: Literal["confirmed", "voided", "refunded"] | None = Field(
        None, description="Only paid (confirmed), voided or refund lines."
    )
    recorded_from: date | None = Field(
        None, description="Only purchases on or after this day."
    )
    recorded_to: date | None = Field(
        None, description="Only purchases on or before this day."
    )
    sort: PurchaseSort = Field(
        "recorded_at", description="The column to order by; the id breaks ties."
    )
    descending: bool = Field(True, description="Newest (or highest) first.")


class DivergencesIn(PageIn):
    search: str | None = Field(
        None, max_length=200, description="Text to look for in the customers' names."
    )


class PurchaseRecordIn(Schema):
    customer_id: UUID | None = Field(
        None, description="The sale's customer; without one nothing is recorded."
    )
    sale_id: UUID | None = Field(
        None,
        description="The sale's id; the same sale counts once. Empty: a manual entry.",
    )
    total: int = Field(ge=0, le=INT8_MAX, strict=True, description="The sale's total, in whole cents.")
    currency: _text(3) = Field("", description="The ISO 4217 currency of the sale.")
    purchased_at: datetime | None = Field(
        None, description="When the sale was paid, if not now."
    )


class PurchaseRefundIn(Schema):
    sale_id: UUID = Field(description="The refunded sale's id.")
    refund_id: UUID = Field(description="The refund's id; the same refund counts once.")
    total: int = Field(ge=0, le=INT8_MAX, strict=True, description="What came back, in whole cents.")
    reason: _text(500) = Field("", description="Why it was refunded.")
    refunded_at: datetime | None = Field(None, description="When it was refunded, if not now.")


class PurchaseVoidIn(Schema):
    sale_id: UUID = Field(description="The voided sale's id.")
    reason: _text(500) = Field("", description="Why the sale was voided.")


class PurchaseRow(Schema):
    id: UUID = Field(description="The entry's id.")
    customer_id: UUID = Field(description="The customer's id.")
    sale_id: UUID | None = Field(description="The sale's id; empty for a manual entry.")
    amount: int = Field(
        description="The amount, in cents; negative on a refund line.",
        json_schema_extra={"money": True},
    )
    currency: str = Field(description="The currency.")
    currency_decimals: int | None = Field(
        description="The decimals of its currency as the server counts them (0 in JPY); empty without a currency."
    )
    status: Literal["confirmed", "voided", "refunded"] = Field(
        description="Paid (confirmed), voided, or a refund of the sale (refunded)."
    )
    recorded_at: datetime = Field(description="When it was paid.")
    voided_at: datetime | None = Field(description="When it was voided.")
    void_reason: str = Field(description="Why it was voided.")

    @staticmethod
    def resolve_currency_decimals(purchase: Purchase) -> int | None:
        return _decimals(purchase.currency)


PurchasePage = Page[PurchaseRow]


class DivergenceRow(Schema):
    id: UUID = Field(description="The customer's id.")
    name: str = Field(description="Name.")
    total_purchases: int = Field(description="Purchases on the card.")
    total_spent: int = Field(description="Spent on the card, in cents.", json_schema_extra={"money": True})
    ledger_purchases: int = Field(description="Paid purchases in its history.")
    ledger_spent: int = Field(description="Paid amount in its history, in cents.", json_schema_extra={"money": True})


DivergencePage = Page[DivergenceRow]


class PurchaseRecordOut(Schema):
    sale_id: UUID | None = Field(description="The sale's id.")
    recorded: bool = Field(
        description="Whether it was recorded now (false: no customer, not live, or already in)."
    )


class PurchaseRefundOut(Schema):
    sale_id: UUID = Field(description="The sale's id.")
    refund_id: UUID = Field(description="The refund's id.")
    refunded: bool = Field(
        description="Whether it was recorded now (false: the sale is not on a card, voided, or the refund already in)."
    )


class PurchaseVoidOut(Schema):
    sale_id: UUID = Field(description="The sale's id.")
    voided: bool = Field(
        description="Whether it was voided now (false: unknown or already voided)."
    )
