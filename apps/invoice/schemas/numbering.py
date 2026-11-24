"""Schemas of the year's numbering: whether it is set up, its gaps and the numbers it gave.
"""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema

from apps.invoice.models import SERIES_CODE_MAX_LENGTH
from apps.invoice.schemas.fields import SEARCH, Page, PageIn


class NumberingStatusIn(Schema):
    """Whether this year's numbering is set up."""


class GapsIn(PageIn):
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this series code."
    )
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")


class AllocationsIn(PageIn):
    search: str | None = Field(
        None, max_length=120, description=SEARCH + " Number or series code."
    )
    code: str | None = Field(
        None, max_length=SERIES_CODE_MAX_LENGTH, description="Only this series code."
    )
    year: int | None = Field(None, ge=2000, le=2999, description="Only this year.")


class NumberingStatusOut(Schema):
    fiscal_year: int
    ordinary_series: int
    rectifying_series: int
    default_series: int
    total_series: int
    configured: bool = Field(
        description="This year has an ordinary series and a rectifying one."
    )


class GapOut(Schema):
    series_code: str
    year: int
    after_sequence: int
    missing_from: int
    next_recorded: int
    missing_count: int


class AllocationOut(Schema):
    series_code: str
    year: int
    sequence: int
    number: str
    invoice_id: UUID
    invoice_type: str
    issued_at: dt.datetime


GapPage = Page[GapOut]
AllocationPage = Page[AllocationOut]
