"""Schemas of the commissions: who can earn one, with their rate, and what each one earned in a period."""

import datetime as dt
from decimal import Decimal
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.staff.schemas.fields import END_BEFORE_START, MAX_AVAILABILITY_DAYS, RANGE_TOO_LONG, Page, PageIn, Search

PERIOD_BOTH_DAYS = _("A period of your own needs its first and its last day.")

#: A record's status as the commission report shows it: someone who left still earned what they sold.
RecordStatus = Literal["active", "inactive", "on_leave", "terminated"]
#: The commission report's periods, counted in business days up to today.
CommissionPeriod = Literal["today", "yesterday", "this_week", "this_month"]


class CommissionSummaryIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the name.")


class CommissionReportIn(Schema):
    period: CommissionPeriod = Field(
        "today",
        description="today (the default), yesterday, this_week (from Monday) or this_month (from the 1st), "
        "in business days up to today. date_from and date_to replace it.",
    )
    date_from: dt.date | None = Field(
        None, description="A period of your own: its first business day (YYYY-MM-DD), with date_to."
    )
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="A period of your own: its last business day (YYYY-MM-DD), at most 731 days after date_from.",
    )

    @field_validator("date_to")
    @classmethod
    def _own_period(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if (start is None) != (value is None):
            raise ValueError(str(PERIOD_BOTH_DAYS))
        if start is not None and value is not None:
            if value < start:
                raise ValueError(str(END_BEFORE_START))
            if (value - start).days >= MAX_AVAILABILITY_DAYS:
                raise ValueError(str(RANGE_TOO_LONG))
        return value


class CommissionOut(Schema):
    """Who can earn a commission, with their rate. A sale names its professional by the record's id; what
    each one earned in a period is ``staff.commission.report``."""

    id: UUID = Field(description="The staff record's id.")
    user_id: UUID | None = Field(
        description="The business user's id; null when the record has none."
    )
    full_name: str
    role_id: UUID | None
    role_name: str | None
    commission_rate: Decimal = Field(
        description="Commission, in percent: commission = gross x rate / 100."
    )


CommissionPage = Page[CommissionOut]


class CommissionReportRow(Schema):
    member_id: UUID = Field(description="The staff record's id.")
    full_name: str
    role_name: str | None
    status: RecordStatus = Field(
        description="active or on_leave (who can earn a commission); inactive or terminated when they sold in the period."
    )
    commission_rate: Decimal = Field(description="Commission, in percent.")
    sold: int = Field(
        description="What they sold in the period, refunds and the vouchers they sold taken off and the value of the "
        "voucher sessions they did added, in cents.", json_schema_extra={"money": True}
    )
    commission: int = Field(
        description="sold x rate / 100, in cents, rounded half up once.",
        json_schema_extra={"money": True},
    )


class CommissionReportOut(Schema):
    date_from: dt.date = Field(description="The period's first business day.")
    date_to: dt.date = Field(description="The period's last business day.")
    sales_available: bool = Field(
        description="False when the business has no Sales: there is nothing to work a commission out from."
    )
    rows: list[CommissionReportRow] = Field(
        description="Everyone who can earn a commission (active or on leave), also without sales, and whoever "
        "sold in the period though inactive or terminated, by name."
    )
    total_sold: int = Field(description="What the rows sold, in cents.", json_schema_extra={"money": True})
    total_commission: int = Field(description="The rows' commissions added up, in cents.", json_schema_extra={"money": True})
