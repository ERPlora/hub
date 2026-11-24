"""Schemas of «Try it» (``flow.flow.test``, ``flow.event.sample``): the automation walked against the last
real event of the business, step by step, executing nothing."""

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from ninja import Field, Schema

from apps.flow import document
from apps.flow.models import EVENT_MAX_LENGTH
from apps.flow.schemas.fields import D_STEPS, D_TRIGGER, D_TRIGGER_IN_WORDS, In
from apps.flow.schemas.steps import Step
from apps.flow.schemas.triggers import Trigger
from base.schemas.assistant import AssistantFieldOut


class TestDocumentIn(In):
    trigger: Trigger = Field(description=D_TRIGGER)
    steps: list[Step] = Field(max_length=document.MAX_STEPS, description=D_STEPS)


class TestIn(In):
    id: UUID | None = Field(None, description="The automation, when it is saved: its permissions are taken from it.")
    document: str = Field(
        max_length=200_000,
        description="The automation to try, saved or not, as JSON text: `{\"trigger\": …, \"steps\": […]}`. "
        + D_TRIGGER_IN_WORDS,
    )


class SampleIn(In):
    event: str = Field(
        min_length=1, max_length=EVENT_MAX_LENGTH, description="The event's name."
    )


class SampleOut(Schema):
    found: bool
    event: str
    at: dt.datetime | None
    payload: dict[str, Any]


class ClauseOut(Schema):
    path: str
    op: str
    value: Any


class PinnedOut(Schema):
    tool: str = Field(description="The tool the step fixes it for, by name.")
    field: str = Field(description="The datum of that tool it fixes.")
    said: AssistantFieldOut | None = Field(
        None,
        description="What it would be in this trial, as the card of the change says it, read as whoever "
        "tries it: a record by its name, never by its id. Null when empty, unknown, or a record they may not read "
        "(the card leaves it out).",
    )
    state: Literal["filled", "empty", "unknown"] = Field(
        description="`filled`; `empty`: its tool would not be used; `unknown`: it reads a step that does not run here."
    )


class TestStepOut(Schema):
    id: str
    kind: str
    outcome: Literal[
        "high_risk",
        "would_run",
        "stops_here",
        "cannot_tell",
        "waits",
        "refused",
        "not_allowed",
        "unavailable",
        "not_reached",
        "skipped",
        "would_call",
        "would_ask",
        "would_ask_assistant",
    ]
    operation: str = ""
    params: dict[str, Any] = {}
    empty: list[str] = []
    unknown: list[str] = []
    errors: dict[str, str] = {}
    failed: list[ClauseOut] = []
    seconds: int | None = None
    #: The data an «Ask the assistant» step fixes, tool by tool (FLOW-F37).
    pinned: list[PinnedOut] = []


class TestOut(Schema):
    sample: SampleOut
    starts: bool
    trigger_failed: list[ClauseOut]
    steps: list[TestStepOut]
