"""Schemas of the runs of an automation (``flow.flow.run``, ``flow.run.*``): running one by hand, the reaction
to an event, and how a run reads."""

import datetime as dt
from typing import Any
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema

from apps.flow.models import EVENT_MAX_LENGTH
from apps.flow.schemas.fields import A_RUN, In, Page, PageIn, RunStatus, TriggerKind
from apps.flow.schemas.flows import FlowRefIn


class RunIn(FlowRefIn):
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="What its steps read as `input.…` (empty: nothing).",
    )


class RunRefIn(In):
    id: UUID = Field(
        title=gettext_noop("Automation run"),
        description="The run's id (its reference in the history).",
        json_schema_extra=A_RUN,
    )


class RunListIn(PageIn):
    limit: int = Field(
        20, ge=1, le=100, description="How many runs to return (1 to 100)."
    )
    flow_id: UUID = Field(description="The automation whose runs to read.")
    status: RunStatus | None = Field(
        None,
        description="Keep the runs in this status: running, waiting, succeeded, stopped, failed or cancelled.",
    )


class ReactIn(In):
    """An event of the outbox, as the relay hands it over."""

    event_id: UUID = Field(
        title=gettext_noop("Reference of what happened"),
        description="The outbox event's id: one run per automation and event.",
    )
    event: str = Field(
        max_length=EVENT_MAX_LENGTH, title=gettext_noop("What happened"), description="The event's name."
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, title=gettext_noop("What brought it"), description="What the event brought."
    )
    actor: str = Field(
        "",
        max_length=128,
        title=gettext_noop("Actor"),
        description="Who caused it (`flow_run:<id>` when a run did; `copy_recovery:<id>` when a recovery from a "
        "separate copy did, which starts no automation).",
    )


class RunOut(Schema):
    id: UUID
    flow_id: UUID
    flow_version: int
    status: RunStatus
    trigger_kind: TriggerKind
    event_name: str
    input: dict[str, Any]
    step_index: int
    steps_total: int
    log: list[dict[str, Any]]
    error_code: str
    error_message: str
    resume_at: dt.datetime | None
    started_at: dt.datetime
    finished_at: dt.datetime | None
    started_by: str
    resumable: bool = Field(
        description="Whether it stopped by an error at a step and can still be resumed there (`flow.run.retry`)."
    )


class RunDetailOut(RunOut):
    label: str = Field(
        description="The words it is named by, in the caller's language: its automation and when it started, as the "
        "History says it («Welcome · Oct 15, 2026, 9:00 PM»)."
    )


class RunPageOut(Page[RunOut]):
    failed: int = Field(
        description="Runs of this automation that stopped by an error, over all pages."
    )


class ReactOut(Schema):
    started: int
    skipped: int
