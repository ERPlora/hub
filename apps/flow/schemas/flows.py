"""Schemas of the automations (``flow.flow.*``): one named by its id or its name, the list, creating,
changing, switching on and granting one, and how an automation reads."""

import datetime as dt
from typing import Annotated, Any, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints, ValidationInfo, field_validator

from apps.flow.models import EVENT_MAX_LENGTH
from apps.flow.schemas.fields import (
    A_DRAFT,
    AN_AUTOMATION,
    D_FLOW,
    D_FLOW_ID,
    D_STEPS,
    D_TRIGGER,
    NO_FLOW,
    STARTS_WITH,
    In,
    Name,
    PageIn,
    Reference,
    RunStatus,
    Search,
    TriggerKind,
    _named,
)
from apps.flow.schemas.steps import Steps
from apps.flow.schemas.triggers import ManualTrigger, Trigger
from base.schemas.assistant import names


class FlowRefIn(In):
    id: UUID | None = Field(
        None, title=gettext_noop("Automation"), description=D_FLOW_ID, json_schema_extra=AN_AUTOMATION
    )
    flow: Reference | None = Field(None, validate_default=True, description=D_FLOW)

    @field_validator("flow")
    @classmethod
    def _flow_named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _named(value, info, "id", NO_FLOW)


class FlowListIn(PageIn):
    search: Search | None = Field(
        None,
        description="Text to look for in the name, the event that starts it or the actions it runs.",
    )
    enabled: bool | None = Field(
        None,
        description="true: only the ones that are on; false: only the paused ones.",
    )
    trigger_kind: TriggerKind | None = Field(
        None,
        description="Keep the ones that start this way: event, schedule, at or manual.",
    )
    sort: Literal["-updated_at", "updated_at", "name", "-name"] = Field(
        "-updated_at",
        description="`-updated_at`: the last touched first; `name`: by name.",
    )


class CreateIn(In):
    name: Name = Field(
        "",
        description="What the owner reads in the list; empty: the Hub's name for an automation without one, in the "
        "person's language.",
    )
    trigger: Trigger = Field(
        default_factory=lambda: ManualTrigger(kind="manual"), title=STARTS_WITH, description=D_TRIGGER
    )
    steps: Steps = Field(default_factory=list, description=D_STEPS)
    draft_id: UUID | None = Field(
        None,
        title=gettext_noop("Draft"),
        description="The assistant's draft it is created from: it is marked as used in the same step.",
        json_schema_extra=A_DRAFT,
    )


class UpdateIn(FlowRefIn):
    name: Name | None = Field(
        None, description="A new name; empty: the Hub's name for an automation without one, in the person's language."
    )
    trigger: Trigger | None = Field(None, title=STARTS_WITH, description=D_TRIGGER)
    steps: Steps | None = Field(None, description=D_STEPS)


class CheckIn(In):
    steps: Steps | None = Field(None, description=D_STEPS)


class CheckOut(Schema):
    calls: int = Field(description="How many calls to another system it checked.")


class EnabledIn(FlowRefIn):
    enabled: bool = Field(description="true: turn it on; false: pause it.")


class GrantIn(FlowRefIn):
    operations: list[
        Annotated[
            str,
            StringConstraints(max_length=96),
            Field(json_schema_extra=names("flow.operation.get", by="operation", name=("label",))),
        ]
    ] = Field(
        max_length=100,
        title=gettext_noop("Permissions"),
        description="The whole list of actions and reads it may run, by name; what is not here is withdrawn.",
    )


class StatusIn(In):
    event: str = Field(
        min_length=1,
        max_length=EVENT_MAX_LENGTH,
        description="The event it starts with.",
    )
    operation: str = Field(
        min_length=1, max_length=96, description="The action it may run."
    )


class LastRunOut(Schema):
    id: UUID
    status: RunStatus
    started_at: dt.datetime


class FixedByAppOut(Schema):
    """What its app fixes today on an automation built from one of its recipes, which is not taken off from the
    automation: the data its «Only when…» has a condition on while it starts on ``event``, and, by step id
    and tool, the fixed data of its «Ask the assistant» steps. Another value of the owner's goes; leaving one out is
    refused (``flow.recipe_fixed``)."""

    app: str
    app_name: str
    event: str
    filter: list[str]
    pinned: dict[str, dict[str, list[str]]]


class FlowOut(Schema):
    id: UUID
    name: str
    enabled: bool
    trigger: dict[str, Any]
    steps: list[dict[str, Any]]
    grants: list[str]
    required_grants: list[str]
    missing_grants: list[str]
    version: int
    next_fire_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by: str
    updated_by: str
    last_run: LastRunOut | None
    fixed_by_app: FixedByAppOut | None = None


class StatusOut(Schema):
    total: int = Field(
        description="Automations that start with the event and may run the action."
    )
    enabled: int = Field(description="Of those, the ones that are on.")
    unfinished: int = Field(
        description="Automations that start with the event and hold no permission yet."
    )
