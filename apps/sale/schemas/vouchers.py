"""Schemas of the vouchers a sale paid for and of the voucher sessions delivered outside the till."""

from datetime import date
from uuid import UUID

from ninja import Field, Schema

from apps.sale.schemas.fields import Cents, Closed


class VoucherSoldIn(Closed):
    sale_id: UUID | None = Field(None, description="The sale that charged the voucher.")
    line_id: UUID | None = Field(
        None, description="The line of it that charged the voucher; only needed when it charged several."
    )
    amount: Cents = Field(description="What was paid for the voucher, VAT included, in cents.")


class VoucherUnsoldIn(Closed):
    line_id: UUID = Field(description="The line that charged the voucher.")
    amount: Cents = Field(description="What was paid for the voucher, VAT included, in cents.")


class VoucherLineOut(Schema):
    sale_id: UUID = Field(description="The sale that charged the voucher.")
    line_id: UUID = Field(description="The line of it that charged the voucher.")


class VoucherSessionIn(Closed):
    session_id: UUID = Field(description="The session of a voucher Services delivered outside the till.")
    staff_id: UUID = Field(description="The member of Staff who did it.")
    value: Cents = Field(description="What it is worth to who did it, VAT included, in cents.")


class VoucherSessionOut(Schema):
    session_id: UUID = Field(description="The session of a voucher delivered outside the till.")
    staff_id: UUID = Field(description="The member of Staff it counts for.")
    business_day: date = Field(description="The business day it counts on.")
    value: int = Field(description="What it counts for, in cents.", json_schema_extra={"money": True})
