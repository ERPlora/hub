"""Schemas of the staff settings: the default working day that proposes the week of a new schedule."""

import datetime as dt

from ninja import Field, Schema
from pydantic import ConfigDict


class SettingsGetIn(Schema):
    pass


class SettingsIn(Schema):
    """The default working day, which proposes the week of a new schedule; only what is sent changes.
    The old module's other eight settings changed nothing and are retired: sending one is refused by
    its name."""

    model_config = ConfigDict(extra="forbid")

    default_work_start: dt.time | None = Field(
        None, description="Working day starts (HH:MM)."
    )
    default_work_end: dt.time | None = Field(
        None, description="Working day ends (HH:MM), after the start."
    )
    default_break_duration: int | None = Field(
        None,
        ge=0,
        le=480,
        description="Break duration, 0 to 480 minutes, shorter than the working day.",
    )


class SettingsOut(Schema):
    default_work_start: str = Field(description="HH:MM.")
    default_work_end: str = Field(description="HH:MM.")
    default_break_duration: int
