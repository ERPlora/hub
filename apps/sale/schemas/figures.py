"""Schemas of what Sales sold: the figures of a period, of today, of the last days and per professional, and
today's business day."""

from datetime import date
from uuid import UUID

from ninja import Field, Schema

from apps.tax.schemas import TerritoryTaxKind


class PeriodIn(Schema):
    date_from: date | None = Field(
        None, description="From this business day (inclusive); empty = since always."
    )
    date_to: date | None = Field(
        None, description="Up to this business day (inclusive); empty = up to today."
    )


class StatsOut(Schema):
    count: int = Field(description="Tickets charged (voided ones aside).")
    total_revenue: int = Field(description="Revenue in cents, refunds taken off.", json_schema_extra={"money": True})
    avg_ticket: int = Field(description="Average ticket in cents.", json_schema_extra={"money": True})
    net_total: int = Field(description="Taxable base in cents.", json_schema_extra={"money": True})
    tax_total: int = Field(description="Tax in cents.", json_schema_extra={"money": True})
    discount_total: int = Field(description="Discounts given, in cents.", json_schema_extra={"money": True})
    refunded_total: int = Field(description="Refunded in cents.", json_schema_extra={"money": True})
    voided_count: int = Field(description="Sales voided.")
    tax_kind: TerritoryTaxKind | None = Field(
        description="The tax the period's sales were declared with, what its tax figure is named by: vat, igic "
        "or ipsi when they all declared it; empty when they declared more than one (or another tax). Without "
        "sales, the business territory's."
    )


class TodayOut(Schema):
    day: date = Field(description="Today's business day.")
    total: int = Field(description="Sold today, in cents.", json_schema_extra={"money": True})
    tickets: int = Field(description="Tickets today.")


class DayTotal(Schema):
    day: date = Field(description="Business day.")
    total: int = Field(description="Sold that day, in cents.", json_schema_extra={"money": True})


class LastDaysOut(Schema):
    rows: list[DayTotal] = Field(
        description="Seven days, oldest first, 0 on a day without sales."
    )


class StaffTotal(Schema):
    staff_id: UUID = Field(description="The member of Staff.")
    sales_count: int = Field(description="Sales where they served at least one line.")
    gross_total: int = Field(description="What their lines charged, in cents.", json_schema_extra={"money": True})
    net_total: int = Field(description="Base of their lines, in cents.", json_schema_extra={"money": True})
    tax_total: int = Field(description="Tax of their lines, in cents.", json_schema_extra={"money": True})
    refunded_total: int = Field(
        description="What the refunds of those sales gave back on their lines, in cents.",
        json_schema_extra={"money": True},
    )
    total_revenue: int = Field(
        description="What their lines charged, refunds taken off, in cents.", json_schema_extra={"money": True}
    )
    voucher_sold_total: int = Field(
        description="What of that paid for vouchers they sold, in cents: the money is the sale's, but it is no "
        "production of theirs: it counts as each session is done.", json_schema_extra={"money": True}
    )
    voucher_total: int = Field(
        description="What the voucher sessions they did are worth, those that came back taken off, in cents: the "
        "voucher's price ÷ its sessions, fixed at each charge. No money of the period: it was paid when it was sold.",
        json_schema_extra={"money": True},
    )
    production_total: int = Field(
        description="Their revenue without the vouchers they sold, plus the voucher sessions they did, in cents: "
        "what their commission is on.", json_schema_extra={"money": True}
    )


class ByStaffOut(Schema):
    rows: list[StaffTotal] = Field(
        description="One row per professional, the one who produced most first."
    )


class BusinessDayOut(Schema):
    today: date = Field(description="Today in the business's time zone.")
