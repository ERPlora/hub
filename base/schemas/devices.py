"""Schemas of the business's devices (``base.device.*``) and the PIN (``base.pin.set``)."""

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


#: A device by its name or, with none, by what it is («Chrome · macOS»), as Settings › Devices says it.
DEVICE_NAMES = ("name", "agent")



class PinSetIn(Schema):
    pin: str = Field(max_length=16)
    current: str = Field(default="", max_length=16, description="The PIN it replaces, when the person has one.")


class PinSetOut(Schema):
    set: bool


class DeviceCurrentIn(Schema):
    """No input: the device of the browser that asks (its cookie)."""


class DeviceCurrentOut(Schema):
    known: bool = Field(description="Whether someone entered this hub with an account from this browser.")
    mode: Literal["shared", "personal"]
    mode_set_by: str = Field(description="Who chose the mode; empty while it is the factory one.")
    mode_set_at: dt.datetime | None


class DeviceModeIn(Schema):
    mode: Literal["shared", "personal"]


class DeviceListIn(Schema):
    """No input: every device of the hub."""


class DeviceOut(Schema):
    id: UUID
    name: str = Field(description="The one the business gave it; empty when it has none.")
    agent: str = Field(description="«Chrome · Android»: how it is recognised before it has a name.")
    mode: Literal["shared", "personal"]
    current: bool = Field(description="The one the person who asks is using.")
    in_use: bool = Field(description="It has a session open now.")
    session_until: dt.datetime | None = Field(description="When its open session ends, if it has one.")
    last_entry_at: dt.datetime = Field(title=gettext_noop("Last used"))
    last_user: str = Field(description="The name of whoever entered on it last.")
    created_at: dt.datetime
    unused: bool = Field(description="Nobody entered on it in 30 days and it is not the one in hand.")


class DeviceListOut(Schema):
    devices: list[DeviceOut] = Field(description="The last entered first.")
    unused: int = Field(description="How many of them «Remove the unused» would remove.")


class DeviceRenameIn(Schema):
    id: UUID = Field(title=gettext_noop("Device"), json_schema_extra=names("base.device.detail", name=DEVICE_NAMES))
    name: str = Field(max_length=80, description="«Bar», «Kitchen»: 60 characters at most once trimmed.")


class DeviceByIdIn(Schema):
    id: UUID = Field(title=gettext_noop("Device"), json_schema_extra=names("base.device.detail", name=DEVICE_NAMES))


class DeviceRemoveOut(Schema):
    removed: int
    yours: bool = Field(description="It was the device of the person who removed it: their session ended too.")


class DevicePruneIn(Schema):
    """No input: the devices nobody entered in 30 days, never the one in hand."""


class DevicePruneOut(Schema):
    removed: int


class DeviceUnusedOut(Schema):
    count: int = Field(title=gettext_noop("Devices to remove"))
    devices: list[Annotated[UUID, Field(json_schema_extra=names("base.device.detail", name=DEVICE_NAMES))]] = Field(
        title=gettext_noop("Which"), description="The last entered first."
    )
