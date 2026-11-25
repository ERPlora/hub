"""Temporary changes: one, how one is named and the list of them."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, ValidationInfo, field_validator

from apps.schedule.engine import MAX_INTERVALS
from apps.schedule.schemas.fields import (
    A_OVERRIDE,
    D_DIRECTION,
    D_INTERVALS,
    D_IS_CLOSED,
    D_SEARCH,
    T_INTERVALS,
    T_OVERRIDE,
    Direction,
    Name,
    Page,
    PageIn,
    Reference,
    Search,
    _not_before,
)
from apps.schedule.schemas.intervals import IntervalIn, IntervalOut, _CheckedIntervals, _intervals_field

WHICH_OVERRIDE = _(
    "Say which temporary change: its id, its reason or a date it covers."
)
D_OVERRIDE_ID = (
    "The id of the temporary change; or say it by reason or date in override."
)
D_OVERRIDE_REF = "The temporary change by its reason (Summer hours) or a date it covers (YYYY-MM-DD), when the id is not given."


class OverrideOut(Schema):
    id: UUID
    start_date: dt.date
    end_date: dt.date
    reason: str
    is_closed: bool
    intervals: list[IntervalOut]


OverridePage = Page[OverrideOut]


class OverrideIn(_CheckedIntervals, Schema):
    model_config = ConfigDict(extra="forbid")

    start_date: dt.date = Field(
        description="First day it applies, YYYY-MM-DD (included)."
    )
    end_date: dt.date = Field(
        description="Last day it applies, YYYY-MM-DD (included); the same date for one day."
    )
    reason: Name = Field(description="Why (Holidays, Summer hours, Works).")
    is_closed: bool = Field(True, description=D_IS_CLOSED + " Closed by default.")
    intervals: list[IntervalIn] = _intervals_field()

    _end_date = field_validator("end_date")(_not_before("start_date"))


class OverrideRefIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(
        None, title=T_OVERRIDE, description=D_OVERRIDE_ID, json_schema_extra=A_OVERRIDE
    )
    override: Reference | None = Field(
        None, validate_default=True, description=D_OVERRIDE_REF
    )

    @field_validator("override")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None and "id" in info.data and info.data["id"] is None:
            raise ValueError(str(WHICH_OVERRIDE))
        return value


class OverridePatchIn(OverrideRefIn):
    """Only what is sent changes; sent intervals replace them all."""

    start_date: dt.date | None = Field(
        None, description="The new first day, YYYY-MM-DD."
    )
    end_date: dt.date | None = Field(None, description="The new last day, YYYY-MM-DD.")
    reason: Name | None = Field(None, description="The new reason.")
    is_closed: bool | None = Field(None, description=D_IS_CLOSED)
    intervals: list[IntervalIn] | None = Field(
        None, max_length=MAX_INTERVALS, title=T_INTERVALS, description=D_INTERVALS
    )


class OverrideListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Reason.")
    start_from: dt.date | None = Field(
        None, description="Only the changes starting on or after this date."
    )
    start_to: dt.date | None = Field(
        None, description="Only the changes starting on or before this date."
    )
    end_from: dt.date | None = Field(
        None, description="Only the changes ending on or after this date."
    )
    end_to: dt.date | None = Field(
        None, description="Only the changes ending on or before this date."
    )
    reason: Search | None = Field(
        None, description="Only the changes whose reason contains this."
    )
    is_closed: bool | None = Field(
        None, description="True: only the closed ones; false: only the open ones."
    )
    sort: Literal["start_date", "end_date", "reason", "is_closed", "id"] = Field(
        "start_date", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=D_DIRECTION)

    _start_to = field_validator("start_to")(_not_before("start_from"))
    _end_to = field_validator("end_to")(_not_before("end_from"))
