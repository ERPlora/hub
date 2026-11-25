"""The settings of the schedule app."""

from ninja import Field, Schema
from pydantic import ConfigDict


class SettingsOut(Schema):
    week_starts_on: int = Field(description="1 = Monday … 7 = Sunday.")
    hours_confirmed: bool = Field(
        description="Somebody saved a day or confirmed the week."
    )
    timezone: str = Field(
        description="The business's time zone (IANA): the clock the hours are read with."
    )


class SettingsIn(Schema):
    model_config = ConfigDict(extra="forbid")

    week_starts_on: int | None = Field(
        None,
        ge=1,
        le=7,
        description="The day the week's table starts on: 1 = Monday … 7 = Sunday.",
    )
