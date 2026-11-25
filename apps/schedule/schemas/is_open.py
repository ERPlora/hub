"""Is it open? The moment asked about, and the answer with the rule that decided it."""

import datetime as dt
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ConfigDict, field_validator

from apps.schedule.engine import parse_when
from apps.schedule.schemas.fields import OUT_OF_CALENDAR, Source, _in_calendar, _out_of_calendar_text

INVALID_MOMENT = _("That date and time are not valid.")
Code = Literal[
    "exception_closed",
    "exception_hours",
    "open_interval",
    "closed_today",
    "overnight_open",
    "outside_hours",
    "no_hours",
]


class IsOpenIn(Schema):
    model_config = ConfigDict(extra="forbid")

    when: str | None = Field(
        None,
        max_length=40,
        description="The moment: an instant with its offset (2026-08-18T08:00:00Z), converted to the business's "
        "clock; or the shop's own wall clock without offset (2026-08-18T10:00 — «tomorrow at ten» is written so). "
        "Empty: now. Between 1900 and 2200.",
    )

    @field_validator("when")
    @classmethod
    def _a_moment(cls, value: str | None) -> str | None:
        try:
            moment = parse_when(value, ZoneInfo("UTC"), dt.datetime.now(dt.UTC))
        except ValueError:
            # A moment that converts out of the calendar (year 1 or 9999 with an offset) is out of it too.
            if _out_of_calendar_text(value):
                raise ValueError(str(OUT_OF_CALENDAR)) from None
            raise ValueError(str(INVALID_MOMENT)) from None
        _in_calendar(moment.date())
        return value


class IsOpenOut(Schema):
    is_open: bool
    code: Code = Field(
        description="Why, as a stable code the caller phrases in its own language."
    )
    source: Source = Field(
        description="Which rule decided: special_day, override, weekly or none."
    )
    rule_id: UUID | None = Field(
        description="The row that decided (null with no rule)."
    )
    intervals: list[str] = Field(
        description="The intervals that explain it, HH:MM–HH:MM."
    )
    timezone: str
    today: dt.date = Field(description="The business's date of the moment.")
    current_time: str = Field(description="The business's time of the moment, HH:MM.")
    reason: str | None = Field(
        description="The name of the special day or the reason of the change that decided."
    )
