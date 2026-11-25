"""Schemas of the device that prints (base's /ws/print): asking for the next job and answering for it."""

from datetime import datetime
from typing import Any
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.printing.schemas.fields import (
    A_JOB,
    ATTEMPT,
    JOB,
    MAX_CLAIM_PRINTERS,
    Closed,
    DeviceError,
    DeviceName,
    JobFormat,
    JobKind,
    PrinterId,
)
from apps.printing.schemas.jobs import JobOut

class JobClaimIn(Closed):
    printers: list[PrinterId] = Field(
        min_length=1,
        max_length=MAX_CLAIM_PRINTERS,
        description="The printers this device reaches (their ids): the ones it was set up with.",
    )
    device: DeviceName = Field(
        description="The device's own id (its deviceId): what proves it is the device set up to print here."
    )


class HostJobOut(Schema):
    id: UUID = Field(description="The job's id: what the device confirms.")
    kind: JobKind = Field(
        description="document → erplora_print (or print_document for a4); test_page → erplora_test_print; drawer → "
        "erplora_open_drawer."
    )
    printer_id: UUID = Field(description="The printer it goes to.")
    target: str = Field(description="The printer id the app's commands take (network:<ip>:<port>…).")
    paper_width: int = Field(description="The printer's paper, 80 or 58 mm.")
    document_type: str = Field(description="The document type the app's renderer paints.")
    document: dict[str, Any] = Field(description="The structured document (the renderer's data): the first copy.")
    copy_document: dict[str, Any] | None = Field(
        description="What every copy after the first prints: a receipt or an invoice marked duplicate (it is no second "
        "original), any other document as it is; none with one copy."
    )
    format: JobFormat = Field(description="receipt or a4.")
    html: str = Field(description="The A4 page (a4 only).")
    copies: int = Field(description="Times to print it.")
    open_drawer: bool = Field(description="Open the drawer after printing.")
    attempts: int = Field(description="Times it has been handed out, this one included.")
    leased_until: datetime = Field(
        description="When the device's time to answer runs out: past it, the job goes back to the queue."
    )


class JobClaimOut(Schema):
    job: HostJobOut | None = Field(description="The next job for this device; none = nothing waiting (idle).")


class JobCompleteIn(Closed):
    job_id: UUID = Field(title=JOB, description="The job the device printed.", json_schema_extra=A_JOB)
    device: DeviceName = Field(description="The own id of the device that printed it: the one that took it.")
    attempt: int = Field(ge=1, title=ATTEMPT, description="The hand-out it printed (the `attempts` it was given).")


class JobFailIn(Closed):
    job_id: UUID = Field(title=JOB, description="The job the device could not print.", json_schema_extra=A_JOB)
    device: DeviceName = Field(description="The own id of the device that could not print it: the one that has it.")
    attempt: int = Field(ge=1, title=ATTEMPT, description="The hand-out that failed (the `attempts` it was given).")
    error: DeviceError = Field(
        title=gettext_noop("Print error"), description="Why, as the device says it (cut at 500 characters)."
    )


class JobAckOut(Schema):
    confirmed: bool = Field(
        description="The answer was taken; false = the job was no longer the device's (it went back to the queue, "
        "was retried or cancelled)."
    )
    job: JobOut = Field(description="The job as it is now.")
