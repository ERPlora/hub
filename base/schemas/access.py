"""Schemas of the way in by PIN and the business's access settings (``base.access.*``)."""

from typing import Literal

from django.utils.translation import gettext_lazy as _
from ninja import Schema
from pydantic import Field, ValidationInfo, field_validator

#: Settings offers asking again after inactivity only with its minutes: none are made up nor the stored ones applied.
SAY_THE_MINUTES = _("Say after how many minutes without use it asks again: 1, 5, 10, 15 or 30.")


# ── The way in: devices, PIN, badge, the business's dial and the person's profile ────────────────────────────────


class AccessDoorIn(Schema):
    """No input: the door of the browser that asks (its device cookie), with a session or without."""


class PinPersonOut(Schema):
    id: str = Field(description="The person's way in on this hub (what a PIN entry names), never their account.")
    name: str
    initials: str


class AccessDoorOut(Schema):
    pin: bool = Field(description="Whether this browser offers the PIN pad: a shared device of the hub that asks.")
    pin_length: int = Field(description="How many digits a PIN of this business has (4 or 6).")
    people: list[PinPersonOut] = Field(description="The faces of the grid; none where the PIN is not offered.")
    wait: int = Field(description="Seconds this address still waits after too many wrong PINs; 0 when it may try.")
    plan_url: str = Field(
        description="erplora.com's plans, for «Upgrade plan» when another device's entry ended this one; empty in "
        "ERPlora's own business, which has no plan."
    )



class AccessSettingsIn(Schema):
    """No input."""


class AccessSettingsOut(Schema):
    pin_policy: Literal["always", "per_shift", "never"]
    pin_inactivity_minutes: Literal[1, 5, 10, 15, 30]
    pin_length: Literal[4, 6]
    can_change: bool = Field(description="Whether the person who asks may change them (who runs the hub).")


class AccessSettingsUpdateIn(Schema):
    """Only the fields sent change (each control saves on its own); at least one."""

    pin_policy: Literal["always", "per_shift", "never"] | None = None
    pin_inactivity_minutes: Literal[1, 5, 10, 15, 30] | None = Field(
        None,
        validate_default=True,
        description="Minutes without use before it asks again; needed with pin_policy always, and only used with it.",
    )
    pin_length: Literal[4, 6] | None = None

    @field_validator("pin_inactivity_minutes")
    @classmethod
    def _minutes_with_always(cls, minutes: int | None, info: ValidationInfo) -> int | None:
        if minutes is None and info.data.get("pin_policy") == "always":
            raise ValueError(str(SAY_THE_MINUTES))
        return minutes


class SessionIdleIn(Schema):
    """No input: the device of the browser that asks (its device cookie)."""


class SessionIdleOut(Schema):
    idle_minutes: int | None = Field(
        description="After how many minutes without use this device's session closes; null: it does not (a personal "
        "device, or a business that does not always ask)."
    )
