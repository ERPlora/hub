"""Schemas of the settings of the room (``table.settings.*``)."""

from typing import Annotated

from ninja import Field, Schema

from apps.table.models import (
    MAX_MINUTES,
    MIN_MINUTES,
)
from apps.table.schemas.fields import In

Minutes = Annotated[int, Field(ge=MIN_MINUTES, le=MAX_MINUTES)]


class SettingsOut(Schema):
    prompt_guests_on_seat: bool = Field(
        description="Ask the guests when seating a table."
    )
    timer_warning_minutes: int = Field(
        description="An open check turns amber after these minutes."
    )
    timer_critical_minutes: int = Field(description="And red after these.")
    reserved_lead_minutes: int = Field(
        description="A reservation paints its table Reserved this long before."
    )
    timezone: str = Field(description="The business's time zone (IANA).")


class SettingsIn(In):
    prompt_guests_on_seat: bool | None = Field(
        None, description="Ask the guests when seating a table."
    )
    timer_warning_minutes: Minutes | None = Field(
        None, description="Amber after these minutes (1 to 600)."
    )
    timer_critical_minutes: Minutes | None = Field(
        None, description="Red after these minutes (1 to 600)."
    )
