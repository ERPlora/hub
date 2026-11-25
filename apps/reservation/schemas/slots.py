"""Schemas of the time slots: their list, writing one, naming it and what the book answers."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator, model_validator

from apps.reservation.models import MAX_GUESTS
from apps.reservation.schemas.fields import A_SLOT, D_LABEL, In, Page, PageIn, Weekday

SAY_WHICH_SLOT = _("Say which slot: its id, or its day of the week and start time.")
SLOT_ENDS_BEFORE = _("A slot has to end after it starts.")

SlotSort = Literal[
    "day_of_week",
    "-day_of_week",
    "start_time",
    "-start_time",
    "end_time",
    "-end_time",
    "max_reservations",
    "-max_reservations",
]


class TimeSlotListIn(PageIn):
    day_of_week: Weekday | None = Field(
        None, description="Only the slots of this weekday (0 = Monday … 6 = Sunday)."
    )
    sort: SlotSort = Field(
        "day_of_week", description="Order; a leading '-' reverses it."
    )


class TimeSlotIn(In):
    day_of_week: Weekday = Field(description="The weekday: 0 = Monday … 6 = Sunday.")
    start_time: dt.time = Field(description="From, HH:MM.")
    end_time: dt.time = Field(description="To, HH:MM (excluded), the same day.")
    max_reservations: int = Field(
        10, ge=1, le=MAX_GUESTS, description="How many reservations fit in it."
    )
    max_covers: int | None = Field(
        None,
        ge=1,
        le=9999,
        description="How many guests fit in it; empty = only the reservations count.",
    )

    @field_validator("end_time")
    @classmethod
    def _ends_after(cls, value: dt.time, info: ValidationInfo) -> dt.time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError(str(SLOT_ENDS_BEFORE))
        return value


class TimeSlotRefIn(In):
    id: UUID | None = Field(
        None,
        title=gettext_noop("Time slot"),
        description="The slot's id.",
        json_schema_extra=A_SLOT,
    )
    day_of_week: Weekday | None = Field(
        None, description="Its weekday, when the id is not known."
    )
    start_time: dt.time | None = Field(
        None, description="Its start, HH:MM, with its weekday."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.id is None and (self.day_of_week is None or self.start_time is None):
            raise ValueError(str(SAY_WHICH_SLOT))
        return self


class TimeSlotOut(Schema):
    id: UUID = Field(description="The slot's id.")
    day_of_week: int = Field(description="0 = Monday … 6 = Sunday.")
    start_time: dt.time = Field(description="From.")
    end_time: dt.time = Field(description="To (excluded).")
    max_reservations: int = Field(description="How many reservations fit.")
    max_covers: int | None = Field(
        description="How many guests fit; empty = not limited."
    )


class TimeSlotDetailOut(TimeSlotOut):
    label: str = Field(description=D_LABEL.format(example="Jueves · 20:00–23:30"))


class TimeSlotPage(Page[TimeSlotOut]):
    pass
