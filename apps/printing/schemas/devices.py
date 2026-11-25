"""Schemas of the devices that print (PRINTING-F18): setting one up, the list, one of them and who covers a
function."""

from datetime import datetime
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import model_validator

from apps.printing.schemas.fields import (
    A_DEVICE,
    MAX_CLAIM_PRINTERS,
    Closed,
    DeviceName,
    Name,
    PageIn,
    PrinterId,
    Usage,
)

NOTHING_TO_CHANGE_DEVICE = _("Say what changes in the device: its name or its printers.")


class DevicePrinterOut(Schema):
    id: UUID = Field(description="The printer's id.")
    name: str = Field(description="Its name.")
    usage: Usage = Field(description="What it prints.")
    is_active: bool = Field(description="It takes jobs.")


class DeviceOut(Schema):
    id: UUID = Field(description="The device's registration id. The device's own id is never shown: it proves the device.")
    name: str = Field(description="Its name, as the business calls it (Counter till).")
    printers: list[DevicePrinterOut] = Field(description="The printers it reaches and prints for, by name.")
    registered_at: datetime = Field(description="When it was set up to print.")
    registered_by: str = Field(description="Who set it up.")
    last_seen_at: datetime | None = Field(
        description="When it last gave news: set up from it, connected to print (each beat) or asked for a job; none = "
        "never yet. Without news for 90 s it counts as off."
    )
    this_device: bool = Field(description="It is the device asking.")


class DeviceRegisterIn(Closed):
    name: Name = Field(description="The device's name, as the business calls it: Counter till, Kitchen tablet.")
    printers: list[PrinterId] = Field(
        max_length=MAX_CLAIM_PRINTERS, description="The active printers this device reaches and prints for (their ids)."
    )


class DeviceRefIn(Closed):
    device_id: UUID = Field(
        title=gettext_noop("Device"),
        description="The device's registration id (printing.device.list).",
        json_schema_extra=A_DEVICE,
    )


class DeviceUpdateIn(DeviceRefIn):
    name: Name | None = Field(None, description="Its new name.")
    printers: list[PrinterId] | None = Field(
        None, max_length=MAX_CLAIM_PRINTERS, description="The active printers it reaches from now on (their ids)."
    )

    @model_validator(mode="after")
    def _changes(self):
        if self.name is None and self.printers is None:
            raise ValueError(str(NOTHING_TO_CHANGE_DEVICE))
        return self


class DeviceListIn(PageIn):
    pass


class CoverageIn(Closed):
    usage: Usage = Field(description="The function: receipt, kitchen, bar or label.")


class CoverageOut(Schema):
    usage: Usage = Field(description="The function asked about.")
    configured: bool = Field(
        description="A device set up here (not retired) reaches an active printer of this function on receipt paper: "
        "its papers come out, whether that device is on right now or not."
    )
    count: int = Field(
        description="Its jobs that have waited a minute or more with no device on to print them: their printer is "
        "reached by no device seen in the last 90 s, or they wait for a printer of their function and paper that none "
        "reaches."
    )


class DeviceGetIn(Closed):
    device: DeviceName = Field(description="The device's own id, as its hello says it (base's /ws/print).")


class DeviceSeenIn(Closed):
    device: DeviceName = Field(description="The device's own id, as its hello says it (base's /ws/print).")


class DeviceSeenOut(Schema):
    seen: bool = Field(description="A device set up here (not retired) has that id: it is there now.")


class DeviceGetOut(Schema):
    device: DeviceOut | None = Field(description="The device set up with that id; none = not set up here, or retired.")
    retired: bool = Field(
        description="It was set up here and retired: it prints nothing, and printing from it does not set it up "
        "again; only setting it up again from the device brings it back."
    )
