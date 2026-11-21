"""The document of an automation, its steps: each kind of step and what it reads, and what is wrong with the
steps as a whole (repeated ids, data that no earlier step leaves)."""

from typing import Annotated, Any, Literal

from live.operations import NAME_RE
from ninja import Field
from pydantic import AfterValidator, StringConstraints, field_validator

from apps.flow import document
from apps.flow.schemas.fields import (
    BAD_ACTION,
    BAD_HEADER,
    BAD_URL,
    CALL_ONLY,
    D_CONDITION,
    DUPLICATE_STEP,
    NO_ACTION,
    NO_COMPARISON,
    STEP_READS_LATER,
    STEP_READS_NOTHING,
    Condition,
    In,
    QuestionRole,
    StepId,
    _text,
)

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
InputName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
D_PINNED = (
    "Data a tool always gets, fixed by the automation: `{tool: {input: value}}`, a tool of `tools` and an input of "
    "that tool, each value as in a step's `params` (a literal, a path such as `steps.s1.id` or text with `{{…}}`), "
    "filled in when it runs. The assistant never sees them and can neither change nor leave them out: what it sends "
    "for them is replaced. A tool whose fixed datum is empty when it runs is not used. E.g. "
    '`{"reservation.reservation.cancel": {"on_behalf_of": "{{steps.s1.id}}"}}`: it only cancels on behalf of the '
    "customer an earlier step read."
)


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
    pinned: Annotated[dict[OperationName, dict[InputName, Any]], Field(max_length=20)] | None = Field(
        None, description=D_PINNED
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
    # The data it looks at and the data it compares with.
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
        return reads + document.references([step.prompt, step.pinned or {}])
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
        found += document.references([step.prompt, step.pinned or {}])
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
