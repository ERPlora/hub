"""What ``printing.device.health`` answers: whether the station of a function answers now."""

from typing import Literal

from ninja import Field, Schema

from apps.printing.schemas.fields import Usage

StationState = Literal["ok", "no_signal", "not_configured"]


class DeviceHealthOut(Schema):
    usage: Usage = Field(description="The function asked about.")
    state: StationState = Field(
        description="ok: a device set up here that reaches an active printer of this function on receipt paper gave "
        "news in the last 90 s; no_signal: there is such a device, but none gave news in the last 90 s; "
        "not_configured: there is none."
    )
