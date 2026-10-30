"""Input and output schemas of the flow app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

The document of an automation is a ``trigger`` and its ``steps`` (``document.py`` reads them). Every
input refuses a field it does not declare. A refusal of a step names it (``steps.<n>.<kind>.<field>``),
so the editor puts it next to the step. An automation is named by its id or its name: the assistant is
used by voice («activate the welcome automation»).

What a step names (an action, a read, an event) is checked against the apps that are active in
``services.py``: a schema knows the shape, not the business.

Each id a write takes is marked with the read that names its record (``names``, base/assistant.py ``REFERS``,
checked at start by ``base.E009``): the assistant's card says which automation, draft, run or question, as the person
who confirms reads it, never by the id — an automation and a draft by their name, a run by its automation and when it
started (``label``, as the History says it), a question by what it asks.
"""

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from live.operations import NAME_RE
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    SecretStr,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from apps.flow import document
from base.schemas import AssistantFieldOut, names
from apps.flow.models import EVENT_MAX_LENGTH, NAME_MAX_LENGTH, QUESTION_ROLES, SECRET_NAME_RE, Draft, FlowRun

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
CALL_ONLY = _("Step %(n)s reads «%(path)s»: a secret or the call's key only go in «Call another system».")
BAD_URL = _(
    "Write the address by hand, starting with https:// and its server's name, without a user or a password; "
    "data can only go after the name, in the path or the query."
)
BAD_HEADER = _("«%(name)s» is no header this step can send.")

TriggerKind = Literal["event", "schedule", "at", "manual"]
RunStatus = Literal[*FlowRun.Status.values]
DraftStatus = Literal[*Draft.Status.values]
QuestionRole = Literal[*QUESTION_ROLES]


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

#: How the Automations list names how an automation starts (the assistant's card names each datum by its title).
STARTS_WITH = gettext_noop("Starts with")

#: The marks of the ids of the records a write names (``names``): the read that names each one, and by what.
AN_AUTOMATION = names("flow.flow.detail")
A_DRAFT = names("flow.draft.get")
A_RUN = names("flow.run.get", name=("label",))
A_QUESTION = names("flow.question.get", name=("title",))

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
    "(`input.customer_id`) or text with `{{input.name}}` inside. Money is in cents. Every step but a "
    "condition may carry `run_if` (skipped when it does not hold) and an action or a read `on_error` "
    "(`continue`: its failure does not stop the run). `ask` asks a person first (`title`, `details`, `role` "
    "'' / manager / employee, `hours` 1 to 720, `on_no` stop / continue, `on_timeout` no / stop / continue) "
    "and leaves `approved`, `expired`, `note` and `answered_by`."
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


D_RUN_IF = (
    "«Only if…»: when these comparisons do not all hold the step is skipped (later steps read "
    "`steps.<id>.skipped`) and the run goes on. " + D_CONDITION
)
D_ON_ERROR = (
    "What a failure of this step does: `stop` (none: the run stops with its reason) or `continue` (the "
    "failure is written in the step, later steps read `steps.<id>.failed` and `steps.<id>.error_code`, and "
    "the run goes on)."
)


class _OperationStep(In):
    id: StepId = Field(
        description="The step's id; later steps read what it leaves as `steps.<id>.<field>`."
    )
    run_if: Condition | None = Field(None, description=D_RUN_IF)
    on_error: Literal["stop", "continue"] | None = Field(None, description=D_ON_ERROR)
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
    run_if: Condition | None = Field(None, description=D_RUN_IF)
    kind: Literal["delay"] = Field(description="Wait, counted from the previous step.")
    seconds: int = Field(
        ge=document.MIN_DELAY_SECONDS,
        le=document.MAX_DELAY_SECONDS,
        description="How long, in seconds: a minute (60) to 30 days (2592000).",
    )


HeaderName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")]
#: Headers the Hub writes itself (or that HTTP forbids a caller to set).
OWN_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection"})


class HttpStep(In):
    id: StepId = Field(description="The step's id; later steps read `steps.<id>.status` and `steps.<id>.body`.")
    kind: Literal["http"] = Field(description="Call another system: an https request, after the step's permission.")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = Field("POST", description="The HTTP method.")
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] = Field(
        description="The address: https:// and its host written by hand; `{{…}}` data only in the path or the "
        "query (percent-encoded). Its origin is the permission it asks for (`http:https://host`)."
    )
    headers: dict[HeaderName, Annotated[str, StringConstraints(max_length=4000)]] = Field(
        default_factory=dict,
        max_length=20,
        description="Headers to send; a value may read `{{secret.NAME}}` and `{{run.idempotency_key}}`.",
    )
    body: Annotated[str, StringConstraints(max_length=65536)] = Field(
        "", description="What to send, as text (a datum inserted in a JSON body is JSON-escaped)."
    )
    timeout: int = Field(10, ge=1, le=30, description="Seconds to wait for the answer, 1 to 30.")
    run_if: Condition | None = Field(None, description=D_RUN_IF)
    on_error: Literal["stop", "continue"] | None = Field(None, description=D_ON_ERROR)

    @field_validator("url")
    @classmethod
    def _plain_https(cls, value: str) -> str:
        if document.literal_origin(value) is None:
            raise ValueError(str(BAD_URL))
        return value

    @field_validator("headers")
    @classmethod
    def _own_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for name in value:
            if name.lower() in OWN_HEADERS:
                raise ValueError(str(BAD_HEADER) % {"name": name})
        return value


class AskStep(In):
    id: StepId = Field(description="The step's id; later steps read `steps.<id>.approved`, `.expired`, `.note`.")
    kind: Literal["ask"] = Field(description="Ask someone first: the run waits for a person's yes or no.")
    title: _text(300, 1) = Field(description="The question, with `{{…}}` data filled in when it is asked.")
    details: _text(2000) = Field("", description="More words under the question, with `{{…}}` data.")
    role: QuestionRole = Field(
        "", description="Who answers: '' whoever runs the business, `manager` or `employee` (they always can too)."
    )
    hours: int = Field(72, ge=1, le=720, description="How long to wait for the answer: 1 hour to 30 days.")
    on_no: Literal["stop", "continue"] = Field("stop", description="A no: `stop` the run here or `continue`.")
    on_timeout: Literal["no", "stop", "continue"] = Field(
        "no", description="Nobody answered in time: `no` (what a no does), `stop` or `continue`."
    )
    run_if: Condition | None = Field(None, description=D_RUN_IF)


OperationName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=96, pattern=NAME_RE.pattern)]


class AssistantStep(In):
    id: StepId = Field(
        description="The step's id; later steps read `steps.<id>.text` (what the assistant answered) and, when a change "
        "waited for a person, `.approved`, `.note` and `.answered_by`."
    )
    kind: Literal["assistant"] = Field(
        description="Ask the assistant: with nobody in front, it does the task with the reads and actions the step "
        "names and the automation was granted."
    )
    prompt: _text(4000, 1) = Field(description="What it is asked to do, with `{{…}}` data filled in when it runs.")
    tools: list[OperationName] = Field(
        default_factory=list,
        max_length=20,
        description="The reads and actions it may use, by name: each one is a permission of the automation.",
    )
    mode: Literal["ask", "auto"] = Field(
        "ask",
        description="`ask`: a change it wants waits in «Waiting for your answer» for a yes; `auto`: it makes it on its "
        "own, as the automation. A read never waits.",
    )
    max_rounds: int = Field(6, ge=1, le=10, description="Most times it may answer before it must be done: 1 to 10.")
    run_if: Condition | None = Field(None, description=D_RUN_IF)
    on_error: Literal["stop", "continue"] | None = Field(None, description=D_ON_ERROR)


Step = Annotated[
    CommandStep | QueryStep | ConditionStep | DelayStep | HttpStep | AskStep | AssistantStep, Field(discriminator="kind")
]
DraftStep = Annotated[
    CommandStep | ConditionStep | DelayStep, Field(discriminator="kind")
]


def _condition_reads(condition: dict) -> list[str]:
    # The data it looks at and the data it compares with (hub#1712).
    return [*condition, *document.references(list(condition.values()))]


def _reads(step: Any) -> list[str]:
    reads = _condition_reads(step.run_if) if getattr(step, "run_if", None) else []
    if step.kind in ("command", "query"):
        return reads + document.references(step.params)
    if step.kind == "condition":
        return _condition_reads(step.when)
    if step.kind == "http":
        texts = document.references([step.url, *step.headers.values(), step.body])
        return reads + [path for path in texts if not document.CALL_ONLY_RE.match(path)]
    if step.kind == "ask":
        return reads + document.references([step.title, step.details])
    if step.kind == "assistant":
        return reads + document.references(step.prompt)
    return reads


def _call_only(step: Any) -> list[str]:
    """What a step reads of what only a call's texts may read (a secret, the call's key): anything in a
    condition, an «Only if…» (a call's own included) or the values of any other step."""
    found = _condition_reads(step.run_if) if getattr(step, "run_if", None) else []
    if step.kind in ("command", "query"):
        found += document.references(step.params)
    elif step.kind == "condition":
        found += _condition_reads(step.when)
    elif step.kind == "ask":
        found += document.references([step.title, step.details])
    elif step.kind == "assistant":
        found += document.references(step.prompt)
    return [path for path in found if path.startswith(("secret.", "run."))]


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
        for path in _call_only(step):
            problems.append(str(CALL_ONLY) % {"n": number, "path": path})
        for path in _reads(step):
            if path.startswith(("secret.", "run.")) and step.kind != "http":
                continue
            if not document.is_path(path):
                problems.append(str(STEP_READS_NOTHING) % {"n": number, "path": path})
            elif path.startswith("steps.") and path.split(".")[1] not in leaves:
                problems.append(str(STEP_READS_LATER) % {"n": number, "path": path})
        if step.kind in ("command", "query", "http", "ask", "assistant"):
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
    id: UUID | None = Field(None, description=D_FLOW_ID, json_schema_extra=AN_AUTOMATION)
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
        None, description="A new name; empty: «Untitled automation»."
    )
    trigger: Trigger | None = Field(None, title=STARTS_WITH, description=D_TRIGGER)
    steps: Steps | None = Field(None, description=D_STEPS)


class EnabledIn(FlowRefIn):
    enabled: bool = Field(description="true: turn it on; false: pause it.")


class GrantIn(FlowRefIn):
    operations: list[Annotated[str, StringConstraints(max_length=96)]] = Field(
        max_length=100,
        title=gettext_noop("Permissions"),
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


class RunRefIn(In):
    id: UUID = Field(description="The run's id (its reference in the history).", json_schema_extra=A_RUN)


class RecordCallIn(In):
    """How a call of a run ended (``apps.flow.http.Reply``), its secrets already hidden."""

    id: UUID = Field(description="The run's id.")
    kind: Literal["ok", "status", "blocked", "invalid", "failed", "timeout"] = Field(
        title=gettext_noop("How it ended"), description="How it ended."
    )
    status: int | None = Field(None, description="The HTTP status it answered.")
    body: Any = Field(None, title=gettext_noop("Body"), description="What it answered: data for JSON, text otherwise.")
    truncated: bool = Field(False, title=gettext_noop("Truncated"), description="Whether the answer was cut at 1 MiB.")
    detail: str = Field(
        "", max_length=2000, title=gettext_noop("Technical text"), description="What went wrong, technically."
    )


class ToolCallIn(In):
    call_id: str = Field(max_length=200, description="The call's id, as the model gave it.")
    name: str = Field(max_length=200, description="The tool's name, as the gateway names it (`task__task__create`).")
    arguments: str = Field("{}", max_length=200_000, description="Its data, as JSON text.")


class AssistantRoundIn(In):
    id: UUID = Field(description="The run whose «Ask the assistant» step is thinking.")
    text: str = Field("", max_length=200_000, description="What the model said with its calls.")
    calls: list[ToolCallIn] = Field(min_length=1, max_length=64, description="The reads and actions it asked for.")
    continuation: str | None = Field(None, max_length=4096, description="What the gateway gave with the calls.")


class RecordAssistantIn(In):
    id: UUID = Field(description="The run whose «Ask the assistant» step ended.")
    text: str = Field("", max_length=200_000, description="What the assistant answered.")
    failure: str = Field("", max_length=96, description="Why it did not answer: the gateway's code; empty when it did.")


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
    id: UUID = Field(description="The draft's id.", json_schema_extra=A_DRAFT)


class CatalogIn(In):
    pass


class SampleIn(In):
    event: str = Field(
        min_length=1, max_length=EVENT_MAX_LENGTH, description="The event's name."
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
        description="Who caused it (`flow_run:<id>` when a run did).",
    )


class DueIn(In):
    pass


# --- Secrets (FLOW-F26) ------------------------------------------------------------------------------

SecretName = Annotated[str, StringConstraints(pattern=SECRET_NAME_RE)]
D_SECRET_NAME = "The secret's name: upper case letters, digits and _, up to 64 (`STRIPE_KEY`)."


class SecretListIn(In):
    pass


class SecretSetIn(In):
    # A refused value is never echoed in an error (the 422 says why, never what).
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: SecretName = Field(description=D_SECRET_NAME)
    value: Annotated[SecretStr, Field(min_length=1, max_length=4096)] = Field(
        title=gettext_noop("Value"),
        description="The value, typed by the person on the screen; it is never shown again."
    )


class SecretRefIn(In):
    name: SecretName = Field(description=D_SECRET_NAME)


# --- Questions (FLOW-F28 to F30) ----------------------------------------------------------------------


class QuestionListIn(In):
    pass


class QuestionRefIn(In):
    id: UUID = Field(description="The question's id, from `flow.question.list`.", json_schema_extra=A_QUESTION)


class AnswerIn(QuestionRefIn):
    approve: bool = Field(
        title=gettext_noop("Answer"),
        description="true: yes, the automation goes on; false: no, it does what its step says.",
    )
    note: _text(500) = Field("", description="A note for the history, optional.")


# --- Factory recipes (FLOW-F33 to F36) ----------------------------------------------------------------

RecipeRef = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,46}/[a-z][a-z0-9_]{0,47}$")]


class RecipeListIn(In):
    pass


class RecipeRefIn(In):
    recipe: RecipeRef = Field(
        description="The ready-made automation an app brings, as `<app>/<id>` («appointment/customer_cancelled»): "
        "`flow.recipe.list` gives them."
    )


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
    #: Whether «Ask the assistant» may use it (its ``ai=`` offers it to the assistant).
    assistant: bool = False
    #: Whether it needs a person's yes first: only an «Ask the assistant» step with «Ask me first» may use it.
    ask_first: bool = False


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


class ClaimAssistantOut(Schema):
    claimed: bool
    messages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    instructions: str = ""
    continuation: str | None = None


class AssistantRoundOut(Schema):
    go_on: bool
    messages: list[dict[str, Any]] = []
    continuation: str | None = None


class DeletedOut(Schema):
    id: UUID


class ClaimCallOut(Schema):
    """A call a run is about to make, for the process that makes it (never a route: it carries the opened
    secrets, which only travel in memory)."""

    claimed: bool
    method: str = ""
    url: str = ""
    headers: dict[str, str] = {}
    body: str = ""
    timeout: int = 10
    masks: list[str] = []


class SecretOut(Schema):
    id: UUID
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime
    updated_by: str


class QuestionOut(Schema):
    id: UUID
    flow_id: UUID
    flow_name: str
    run_id: UUID
    title: str
    details: str
    role: str = Field(description="Who it was asked of: '' whoever runs the business, `manager` or `employee`.")
    on_no: str
    on_timeout: str
    expires_at: dt.datetime
    created_at: dt.datetime
    fields: list[AssistantFieldOut] = Field(
        default_factory=list,
        description="The data of the change the assistant wants (FLOW-F38), as its confirmation card in the chat says "
        "them, read for whoever asks: a moment in their language at the business's hour, a record by its name only "
        "if they may read it, an amount in cents as `money`; none for a question an «Ask someone first» step asks.",
    )


class QuestionPageOut(Schema):
    rows: list[QuestionOut]


class AnsweredOut(Schema):
    id: UUID = Field(description="The question's id.")
    run_id: UUID
    status: RunStatus = Field(description="How its run is after the answer.")


class SecretPageOut(Schema):
    rows: list[SecretOut]
    available: bool = Field(description="Whether this server can keep and use secrets (it has its key).")


class RecipeGrantOut(Schema):
    operation: str
    reason: str = Field(description="Why it asks for it, in the words of the app that brings it.")


class RecipeInstalledOut(Schema):
    flow_id: UUID
    name: str
    enabled: bool
    outdated: bool = Field(description="Its app brings a newer version than the one it was built or restored from.")
    missing_grants: list[str]
    repair: dict[str, dict[str, Any]] = Field(
        description="The «Only when…» clauses its app added since the version it was built from; empty: nothing to repair."
    )


class RecipeOut(Schema):
    ref: str = Field(description="`<app>/<id>`: what `flow.recipe.enable` and the others take.")
    app: str
    app_name: str
    icon: str
    id: str
    name: str
    summary: str
    description: str
    trigger: dict[str, Any]
    steps: list[dict[str, Any]]
    grants: list[RecipeGrantOut]
    installed: RecipeInstalledOut | None = Field(description="The automation this business built from it, if any.")


class RecipeSetAsideOut(Schema):
    ref: str
    app: str
    app_name: str
    name: str
    code: str = Field(description="`flow.recipe_needs_apps` or `flow.recipe_invalid`.")
    message: str
    apps: list[str] = Field(description="The apps it needs that this business does not have.")


class RecipeListOut(Schema):
    recipes: list[RecipeOut]
    set_aside: list[RecipeSetAsideOut]


class RecipeEnabledOut(Schema):
    created: bool = Field(description="true: it was built now; false: it already existed and was switched on.")
    flow: FlowOut
