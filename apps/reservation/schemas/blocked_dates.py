"""Schemas of the blocked dates: their list, blocking a day or some of its hours, naming one and what the book
answers."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.reservation.schemas.fields import A_BLOCK, D_LABEL, In, Page, PageIn, _text

SAY_WHICH_BLOCK = _("Say which blocked date: its id, or its date.")
BLOCK_NEEDS_HOURS = _("Give the hours it blocks, or block the whole day.")
BLOCK_ENDS_BEFORE = _("The blocked hours have to end after they start.")

BlockedSort = Literal[
    "date", "-date", "reason", "-reason", "is_full_day", "-is_full_day"
]


class BlockedDateListIn(PageIn):
    date_from: dt.date | None = Field(None, description="From this day (included).")
    date_to: dt.date | None = Field(None, description="Until this day (included).")
    is_full_day: bool | None = Field(
        None, description="Only whole days (true) or only some hours (false)."
    )
    sort: BlockedSort = Field("date", description="Order; a leading '-' reverses it.")


class BlockedDateIn(In):
    date: dt.date = Field(description="The day, YYYY-MM-DD.")
    reason: _text(200) = Field(
        "", description="Why: a holiday, a closure, a private event."
    )
    is_full_day: bool = Field(
        True, description="True blocks the whole day; false, only the hours given."
    )
    blocked_from: dt.time | None = Field(
        None,
        validate_default=True,
        description="From, HH:MM, when only some hours are blocked.",
    )
    blocked_until: dt.time | None = Field(
        None,
        validate_default=True,
        description="Until, HH:MM (included), when only some hours are blocked.",
    )

    @field_validator("blocked_from")
    @classmethod
    def _from_given(cls, value: dt.time | None, info: ValidationInfo) -> dt.time | None:
        if info.data.get("is_full_day") is False and value is None:
            raise ValueError(str(BLOCK_NEEDS_HOURS))
        return value

    @field_validator("blocked_until")
    @classmethod
    def _until_after(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if info.data.get("is_full_day") is not False:
            return value
        if value is None:
            raise ValueError(str(BLOCK_NEEDS_HOURS))
        start = info.data.get("blocked_from")
        if start is not None and value <= start:
            raise ValueError(str(BLOCK_ENDS_BEFORE))
        return value


class BlockedDateRefIn(In):
    id: UUID | None = Field(
        None,
        title=gettext_noop("Blocked date"),
        description="The blocked date's id.",
        json_schema_extra=A_BLOCK,
    )
    date: dt.date | None = Field(
        None, description="Its day, YYYY-MM-DD, when the id is not known."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and self.date is None:
            raise ValueError(str(SAY_WHICH_BLOCK))
        return self


class BlockedDateOut(Schema):
    id: UUID = Field(description="The blocked date's id.")
    date: dt.date = Field(description="The day blocked.")
    reason: str = Field(description="Why (holiday, closure, private event).")
    is_full_day: bool = Field(description="True when the whole day is blocked.")
    blocked_from: dt.time | None = Field(
        description="From what time, when only some hours are blocked."
    )
    blocked_until: dt.time | None = Field(description="Until what time (included).")



class BlockedDateDetailOut(BlockedDateOut):
    label: str = Field(
        description=D_LABEL.format(example="15 oct 2026 · 13:00–16:00")
    )


class BlockedDatePage(Page[BlockedDateOut]):
    pass
