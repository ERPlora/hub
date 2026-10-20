"""Input and output schemas of the flow app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

The document of an automation is a ``trigger`` and its ``steps`` (``document.py`` reads them). Every
input refuses a field it does not declare. A refusal of a step names it (``steps.<n>.<kind>.<field>``),
so the editor puts it next to the step. An automation is named by its id or its name: the assistant is
used by voice («activate the welcome automation»).

What a step names (an action, a read, an event) is checked against the apps that are active in
``services.py``: a schema knows the shape, not the business.
"""

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.operations import NAME_RE
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.flow import document
from apps.flow.models import EVENT_MAX_LENGTH, NAME_MAX_LENGTH, Draft, FlowRun

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
NO_FLOW = _("Say which automation: its id or its name.")
NO_EVENT = _("Choose what has to happen for it to start.")
BAD_EVENT = _("That is no event name.")
NO_ACTION = _("Choose what this step does.")
BAD_ACTION = _("That is no action name.")
NO_WEEKDAY = _("Choose the day of the week.")
NO_MONTH_DAY = _("Choose the day of the month.")
BAD_PATH = _("«%(path)s» is no data of this automation.")
BAD_OPERATOR = _("«%(op)s» is no way of comparing.")
NO_COMPARISON = _("Add at least one comparison.")
FILTER_INPUT_ONLY = _("«Only when…» reads only what the event brings (input.…).")
DUPLICATE_STEP = _("Two steps have the id «%(id)s».")
STEP_READS_NOTHING = _(
    "Step %(n)s reads «%(path)s», which is no data of this automation."
)
STEP_READS_LATER = _("Step %(n)s reads «%(path)s», which no earlier step leaves.")

TriggerKind = Literal["event", "schedule", "at", "manual"]
RunStatus = Literal[*FlowRun.Status.values]
DraftStatus = Literal[*Draft.Status.values]


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(NAME_MAX_LENGTH)
Search = _text(100)
Reference = _text(NAME_MAX_LENGTH, 1)
Note = _text(500, 1)
StepId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,23}$")]
Time = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]

# Field descriptions shared by several schemas (the assistant reads them).
D_FLOW_ID = "The automation's id. Give it, or its name in `flow`."
D_FLOW = "The automation's name, or part of it, when the id is not known («welcome», «cash close»)."
D_TRIGGER = (
    "When it starts, by `kind`: `event` (something happens: `event` is its name, as "
    "`sale.sale.completed`, and `filter` an optional condition on what it brings), `schedule` "
    "(`every` day, week or month at `time` HH:MM in the business's time zone; `weekday` 0=Monday for "
    "a week, `day` 1-31 for a month), `at` (once, at `at`, an ISO date and time with its offset) or "
    "`manual` (only when somebody runs it)."
)
D_STEPS = (
    "What it does, in order, at most 50. A step has an `id` (a-z, 0-9, _; later steps read its output as "
    "`steps.<id>.<field>`) and a `kind`: `command` (runs the action `operation` of another app with "
    "`params`), `query` (reads with the query `operation` and `params`, `result` `first` keeps the first "
    "row's fields and `count` only how many; both leave `found` and `count`), `condition` (`when`: every "
    "comparison must hold, or the run ends there without error) or `delay` (`seconds`, 60 to 2592000, "
    "counted from the previous step). A value in `params` is a literal, a path that keeps its type "
    "(`input.customer_id`) or text with `{{input.name}}` inside. Money is in cents."
)
D_CONDITION = (
    "Comparisons, all at once: `{path: {operator: value}}` with eq, neq, in, exists, contains, gt, gte, "
    "lt or lte; a field that is not there never matches, except with `exists: false`."
)


def _condition(value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for path, comparisons in value.items():
        if not document.is_path(path):
            raise ValueError(str(BAD_PATH) % {"path": path})
        if not comparisons:
            raise ValueError(str(NO_COMPARISON))
        for operator in comparisons:
            if operator not in document.OPERATORS:
                raise ValueError(str(BAD_OPERATOR) % {"op": operator})
    return value


Condition = Annotated[dict[str, dict[str, Any]], AfterValidator(_condition)]


def _named(
    value: str | None, info: ValidationInfo, id_field: str, message
) -> str | None:
    """The text reference is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(message))
    return value


class In(Schema):
    """Every input refuses a field it does not declare (a filter or a field that does not exist)."""

    model_config = ConfigDict(extra="forbid")


class PageIn(In):
    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, for the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int = Field(description="Rows that match, over all pages.")
    limit: int
    offset: int


# --- The document: its trigger ----------------------------------------------------------------------


class EventTrigger(In):
    kind: Literal["event"] = Field(description="Something happens in the business.")
    event: str = Field(
        max_length=EVENT_MAX_LENGTH,
        description="The event's name (`sale.sale.completed`).",
    )
    filter: Condition = Field(
        default_factory=dict, description="«Only when…»: " + D_CONDITION
    )

    @field_validator("event")
    @classmethod
    def _event(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(str(NO_EVENT))
        if not NAME_RE.match(value):
            raise ValueError(str(BAD_EVENT))
        return value

    @field_validator("filter")
    @classmethod
    def _input_only(cls, value: dict) -> dict:
        if any(not path.startswith("input.") for path in value):
            raise ValueError(str(FILTER_INPUT_ONLY))
        return value


class ScheduleTrigger(In):
    kind: Literal["schedule"] = Field(
        description="On a schedule, in the business's time zone."
    )
    every: Literal["day", "week", "month"] = Field(
        description="How often: day, week or month."
    )
    time: Time = Field(description="At what time, HH:MM (24 h).")
    weekday: int | None = Field(
        None, ge=0, le=6, description="For `week`: the day, 0 = Monday … 6 = Sunday."
    )
    day: int | None = Field(
        None,
        ge=1,
        le=31,
        description="For `month`: the day of the month (a month without it is skipped).",
    )

    @model_validator(mode="after")
    def _its_day(self) -> "ScheduleTrigger":
        if self.every == "week" and self.weekday is None:
            raise ValueError(str(NO_WEEKDAY))
        if self.every == "month" and self.day is None:
            raise ValueError(str(NO_MONTH_DAY))
        return self


class AtTrigger(In):
    kind: Literal["at"] = Field(description="Once, at a date and time.")
    at: AwareDatetime = Field(
        description="When, as an ISO date and time with its offset."
    )


class ManualTrigger(In):
    kind: Literal["manual"] = Field(description="Only when somebody runs it.")


Trigger = Annotated[
    EventTrigger | ScheduleTrigger | AtTrigger | ManualTrigger,
    Field(discriminator="kind"),
]


# --- The document: its steps ------------------------------------------------------------------------


class _OperationStep(In):
    id: StepId = Field(
        description="The step's id; later steps read what it leaves as `steps.<id>.<field>`."
    )
    operation: str = Field(
        max_length=96, description="The operation of another app, by its name."
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="What the operation receives: literals, paths (`input.total`) or text with `{{…}}`.",
    )

    @field_validator("operation")
    @classmethod
    def _operation(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(str(NO_ACTION))
        if not NAME_RE.match(value):
            raise ValueError(str(BAD_ACTION))
        return value


class CommandStep(_OperationStep):
    kind: Literal["command"] = Field(
        description="Do something: run an action of another app."
    )


class QueryStep(_OperationStep):
    kind: Literal["query"] = Field(
        description="Look something up: run a read of another app."
    )
    result: Literal["first", "count"] = Field(
        "first",
        description="`first`: the first row's fields; `count`: only how many. Both leave found and count.",
    )


class ConditionStep(In):
    id: StepId = Field(description="The step's id.")
    kind: Literal["condition"] = Field(
        description="Only continue if: otherwise the run ends here, without error."
    )
    when: Condition = Field(description=D_CONDITION)

    @field_validator("when")
    @classmethod
    def _not_empty(cls, value: dict) -> dict:
        if not value:
            raise ValueError(str(NO_COMPARISON))
        return value


class DelayStep(In):
    id: StepId = Field(description="The step's id.")
    kind: Literal["delay"] = Field(description="Wait, counted from the previous step.")
    seconds: int = Field(
        ge=document.MIN_DELAY_SECONDS,
        le=document.MAX_DELAY_SECONDS,
        description="How long, in seconds: a minute (60) to 30 days (2592000).",
    )


Step = Annotated[
    CommandStep | QueryStep | ConditionStep | DelayStep, Field(discriminator="kind")
]
DraftStep = Annotated[
    CommandStep | ConditionStep | DelayStep, Field(discriminator="kind")
]


def _reads(step: Any) -> list[str]:
    if step.kind in ("command", "query"):
        return document.references(step.params)
    if step.kind == "condition":
        # The data it looks at and the data it compares with (hub#1712).
        return [*step.when, *document.references(list(step.when.values()))]
    return []


def document_problems(steps: list[Any]) -> list[str]:
    """What is wrong with ``steps`` as a whole: repeated ids, and data a step reads that is no data of
    the automation or that no earlier step leaves (only actions and reads leave something)."""
    problems: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            problems.append(str(DUPLICATE_STEP) % {"id": step.id})
        seen.add(step.id)
    leaves: set[str] = set()
    for number, step in enumerate(steps, start=1):
        for path in _reads(step):
            if not document.is_path(path):
                problems.append(str(STEP_READS_NOTHING) % {"n": number, "path": path})
            elif path.startswith("steps.") and path.split(".")[1] not in leaves:
                problems.append(str(STEP_READS_LATER) % {"n": number, "path": path})
        if step.kind in ("command", "query"):
            leaves.add(step.id)
    return problems


def _steps(value: list[Any]) -> list[Any]:
    problems = document_problems(value)
    if problems:
        raise ValueError(problems[0])
    return value


Steps = Annotated[
    list[Step], Field(max_length=document.MAX_STEPS), AfterValidator(_steps)
]


# --- Inputs -----------------------------------------------------------------------------------------


class FlowRefIn(In):
    id: UUID | None = Field(None, description=D_FLOW_ID)
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
        description="What the owner reads in the list; empty: «Untitled automation».",
    )
    trigger: Trigger = Field(
        default_factory=lambda: ManualTrigger(kind="manual"), description=D_TRIGGER
    )
    steps: Steps = Field(default_factory=list, description=D_STEPS)
    draft_id: UUID | None = Field(
        None,
        description="The assistant's draft it is created from: it is marked as used in the same step.",
    )


class UpdateIn(FlowRefIn):
    name: Name | None = Field(
        None, description="A new name; empty: «Untitled automation»."
    )
    trigger: Trigger | None = Field(None, description=D_TRIGGER)
    steps: Steps | None = Field(None, description=D_STEPS)


class EnabledIn(FlowRefIn):
    enabled: bool = Field(description="true: turn it on; false: pause it.")


class GrantIn(FlowRefIn):
    operations: list[Annotated[str, StringConstraints(max_length=96)]] = Field(
        max_length=100,
        description="The whole list of actions and reads it may run, by name; what is not here is withdrawn.",
    )


class RunIn(FlowRefIn):
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="What its steps read as `input.…` (empty: nothing).",
    )


class TestDocumentIn(In):
    trigger: Trigger = Field(description=D_TRIGGER)
    steps: list[Step] = Field(max_length=document.MAX_STEPS, description=D_STEPS)


class TestIn(In):
    id: UUID | None = Field(None, description="The automation, when it is saved: its permissions are taken from it.")
    document: str = Field(
        max_length=200_000,
        description="The automation to try, saved or not, as JSON text: `{\"trigger\": …, \"steps\": […]}`. "
        + D_TRIGGER,
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


class RunListIn(PageIn):
    limit: int = Field(
        20, ge=1, le=100, description="How many runs to return (1 to 100)."
    )
    flow_id: UUID = Field(description="The automation whose runs to read.")
    status: RunStatus | None = Field(
        None,
        description="Keep the runs in this status: running, waiting, succeeded, stopped, failed or cancelled.",
    )


class DraftListIn(PageIn):
    pass


class DraftDefinitionIn(In):
    trigger: Trigger | None = Field(
        None, description="When it starts; none: only by hand. " + D_TRIGGER
    )
    steps: Annotated[list[DraftStep], AfterValidator(_steps)] = Field(
        min_length=1,
        max_length=8,
        description="One to eight steps of kind command, condition or delay (never a query). "
        + D_STEPS,
    )


class DraftProposeIn(In):
    name: Reference = Field(
        description="What the owner reads in their list, in their language and words («Call who did not come»)."
    )
    definition: DraftDefinitionIn = Field(
        description="The draft: LINEAR, a condition that does not hold ends the run; no branch, loop or else."
    )
    notes: list[Note] = Field(
        default_factory=list,
        max_length=8,
        description="What you could not work out, one short sentence each, in the owner's language.",
    )


class DraftRefIn(In):
    id: UUID = Field(description="The draft's id.")


class CatalogIn(In):
    pass


class SampleIn(In):
    event: str = Field(
        min_length=1, max_length=EVENT_MAX_LENGTH, description="The event's name."
    )


class ReactIn(In):
    """An event of the outbox, as the relay hands it over."""

    event_id: UUID = Field(
        description="The outbox event's id: one run per automation and event."
    )
    event: str = Field(max_length=EVENT_MAX_LENGTH, description="The event's name.")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="What the event brought."
    )
    actor: str = Field(
        "",
        max_length=128,
        description="Who caused it (`flow_run:<id>` when a run did).",
    )


class DueIn(In):
    pass


# --- Outputs ----------------------------------------------------------------------------------------


class LastRunOut(Schema):
    id: UUID
    status: RunStatus
    started_at: dt.datetime


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


class RunPageOut(Page[RunOut]):
    failed: int = Field(
        description="Runs of this automation that stopped by an error, over all pages."
    )


class DraftOut(Schema):
    id: UUID
    name: str
    definition: dict[str, Any]
    notes: list[str]
    status: DraftStatus
    flow_id: UUID | None
    created_at: dt.datetime
    created_by: str


class StatusOut(Schema):
    total: int = Field(
        description="Automations that start with the event and may run the action."
    )
    enabled: int = Field(description="Of those, the ones that are on.")
    unfinished: int = Field(
        description="Automations that start with the event and hold no permission yet."
    )


class CatalogEventOut(Schema):
    name: str
    app: str
    app_name: str


class FieldOut(Schema):
    name: str
    type: str
    required: bool
    description: str
    choices: list[str]


class CatalogActionOut(Schema):
    name: str
    kind: Literal["command", "query"]
    app: str
    app_name: str
    description: str
    fields: list[FieldOut]
    outputs: list[str]


class CatalogOut(Schema):
    events: list[CatalogEventOut]
    actions: list[CatalogActionOut]


class SampleOut(Schema):
    found: bool
    event: str
    at: dt.datetime | None
    payload: dict[str, Any]


class ClauseOut(Schema):
    path: str
    op: str
    value: Any


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
    ]
    operation: str = ""
    params: dict[str, Any] = {}
    empty: list[str] = []
    unknown: list[str] = []
    errors: dict[str, str] = {}
    failed: list[ClauseOut] = []
    seconds: int | None = None


class TestOut(Schema):
    sample: SampleOut
    starts: bool
    trigger_failed: list[ClauseOut]
    steps: list[TestStepOut]


class ReactOut(Schema):
    started: int
    skipped: int


class DueOut(Schema):
    count: int


class DeletedOut(Schema):
    id: UUID
