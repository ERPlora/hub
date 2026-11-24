"""The document of an automation, its trigger: what has to happen for a run to start (an event, a schedule,
a moment, or somebody running it)."""

from typing import Annotated, Literal

from live.operations import NAME_RE
from ninja import Field
from pydantic import AwareDatetime, field_validator, model_validator

from apps.flow.models import EVENT_MAX_LENGTH
from apps.flow.schemas.fields import (
    BAD_EVENT,
    FILTER_INPUT_ONLY,
    NO_EVENT,
    NO_MONTH_DAY,
    NO_WEEKDAY,
    Condition,
    In,
    Time,
)


class EventTrigger(In):
    kind: Literal["event"] = Field(description="Something happens in the business.")
    event: str = Field(
        max_length=EVENT_MAX_LENGTH,
        description="The event's name (`sale.sale.completed`).",
    )
    filter: Condition = Field(
        default_factory=dict,
        description="«Only when…»: comparisons on what the event brings (`input.…`), as in a condition's `when`.",
    )

    @field_validator("event")
    @classmethod
    def _event(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(str(NO_EVENT))
        if not NAME_RE.match(value):
            raise ValueError(str(BAD_EVENT))
        return value

    @field_validator("filter")
    @classmethod
    def _input_only(cls, value: dict) -> dict:
        if any(not path.startswith("input.") for path in value):
            raise ValueError(str(FILTER_INPUT_ONLY))
        return value


class ScheduleTrigger(In):
    kind: Literal["schedule"] = Field(
        description="On a schedule, in the business's time zone."
    )
    every: Literal["day", "week", "month"] = Field(
        description="How often: day, week or month."
    )
    time: Time = Field(description="At what time, HH:MM (24 h).")
    weekday: int | None = Field(
        None, ge=0, le=6, description="For `week`: the day, 0 = Monday … 6 = Sunday."
    )
    day: int | None = Field(
        None,
        ge=1,
        le=31,
        description="For `month`: the day of the month (a month without it is skipped).",
    )

    @model_validator(mode="after")
    def _its_day(self) -> "ScheduleTrigger":
        if self.every == "week" and self.weekday is None:
            raise ValueError(str(NO_WEEKDAY))
        if self.every == "month" and self.day is None:
            raise ValueError(str(NO_MONTH_DAY))
        return self


class AtTrigger(In):
    kind: Literal["at"] = Field(description="Once, at a date and time.")
    at: AwareDatetime = Field(
        description="When, as an ISO date and time with its offset."
    )


class ManualTrigger(In):
    kind: Literal["manual"] = Field(description="Only when somebody runs it.")


Trigger = Annotated[
    EventTrigger | ScheduleTrigger | AtTrigger | ManualTrigger,
    Field(discriminator="kind"),
]
