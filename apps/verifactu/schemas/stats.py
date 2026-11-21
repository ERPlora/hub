"""The figures of VeriFactu's widgets: compliance, records by status, the queue and the latest events."""

from typing import Literal

from ninja import Field, Schema

from apps.verifactu.schemas.events import EventOut
from apps.verifactu.schemas.fields import EnvironmentCode, StatusCode


class ComplianceSummaryOut(Schema):
    unsent_count: int = Field(
        description="Records not in the AEAT yet (pending or sent without answer)."
    )
    pending_count: int = Field(
        description="Records not accepted: unsent plus rejected."
    )
    rejected_count: int = Field(description="Records the AEAT rejected.")
    accepted_count: int = Field(
        description="Records in the AEAT (accepted, with or without errors)."
    )
    total: int = Field(description="Every record.")
    environment: EnvironmentCode = Field(description="The environment now.")


class StatusCountOut(Schema):
    status: StatusCode = Field(description="A status.")
    label: str = Field(description="Its name in the reader's language.")
    total: int = Field(description="Records in it.")


class RecordsByStatusOut(Schema):
    rows: list[StatusCountOut] = Field(description="One row per status.")


class ContingencySummaryOut(Schema):
    queued_count: int = Field(description="Records in the queue.")
    overdue_count: int = Field(description="Records whose attempt is due now.")
    severity: Literal["ok", "warning", "danger"] = Field(
        description="ok (empty), warning or danger (failing)."
    )


class EventsRecentIn(Schema):
    limit: int = Field(10, ge=1, le=20, description="How many, 1 to 20.")


class EventsOut(Schema):
    rows: list[EventOut] = Field(description="The latest events.")
