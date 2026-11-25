"""The periods nobody books: a holiday, a break, one professional's leave."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.appointment.schemas.agenda import DateRange
from apps.appointment.schemas.fields import (
    A_BLOCK,
    A_MEMBER,
    D_START,
    END_BEFORE_START,
    T_BLOCK,
    In,
    Page,
    Reason,
    Said,
    _text,
)

BlockType = Literal["holiday", "vacation", "break", "maintenance", "other"]


class BlockedTimeCreateIn(In):
    title: _text(200, 1) = Field(description="What it is (e.g. Training, Holiday).")
    block_type: BlockType = Field(
        "other", description="holiday, vacation, break, maintenance or other."
    )
    start: dt.datetime = Field(description=D_START)
    end: dt.datetime = Field(description="When it ends (a whole day: its last day).")
    all_day: bool = Field(
        False, description="True: whole days, from the start's day to the end's day."
    )
    staff_id: UUID | None = Field(
        None, description="Only this professional; empty = the whole business.", json_schema_extra=A_MEMBER
    )
    staff: Said | None = Field(None, description="Only this professional, by name.")
    reason: Reason = Field("", description="Why (optional).")

    @model_validator(mode="after")
    def _order(self):
        if self.end < self.start or (not self.all_day and self.end == self.start):
            raise ValueError(str(END_BEFORE_START))
        return self

    @field_validator("end")
    @classmethod
    def _end(cls, value, info: ValidationInfo):
        start = info.data.get("start")
        if start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value


class BlockedTimeRefIn(In):
    id: UUID = Field(title=T_BLOCK, description="The blocked period's id.", json_schema_extra=A_BLOCK)


class BlockedTimeListIn(DateRange):
    limit: int = Field(100, ge=1, le=100, description="How many rows (1 to 100).")
    offset: int = Field(0, ge=0, description="How many rows to skip.")
    staff_id: UUID | None = Field(
        None, description="This professional's blocks and the whole business's."
    )


class BlockedTimeOut(Schema):
    id: UUID
    title: str
    block_type: BlockType
    start: dt.datetime
    end: dt.datetime
    all_day: bool
    staff_id: UUID | None
    staff_name: str
    reason: str


class BlockedTimeNamedOut(BlockedTimeOut):
    label: str = Field(
        description="How a person names it: its title, its day, its hour (none for a whole day) and its professional."
    )


class BlockedTimePage(Page[BlockedTimeOut]):
    pass
