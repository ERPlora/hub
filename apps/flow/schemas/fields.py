"""What the flow app's schemas share: the base of every input and a page of rows, the field types, the texts
of the refusals, the descriptions the assistant reads, the marks of the ids a write names and the inputs and
outputs of the scheduled passes."""

from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, ConfigDict, StringConstraints, ValidationInfo

from apps.flow import document
from apps.flow.models import NAME_MAX_LENGTH, QUESTION_ROLES, Draft, FlowRun
from base.schemas.assistant import names

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
# Each kind of trigger and of step describes its own data, so a field that holds them says only what they share.
D_TRIGGER = "When it starts, by its `kind`."
#: For an automation sent as JSON text, which carries no trigger schema for the model to read.
D_TRIGGER_IN_WORDS = (
    "When it starts, by `kind`: `event` (something happens: `event` is its name, as "
    "`sale.sale.completed`, and `filter` an optional condition on what it brings), `schedule` "
    "(`every` day, week or month at `time` HH:MM in the business's time zone; `weekday` 0=Monday for "
    "a week, `day` 1-31 for a month), `at` (once, at `at`, an ISO date and time with its offset) or "
    "`manual` (only when somebody runs it)."
)
D_STEPS = (
    "What it does, in order, each step by its `kind`. Every step but a condition may carry `run_if` («Only if…», "
    "comparisons as in a condition's `when`): when they do not all hold, the step is skipped (later steps read "
    "`steps.<id>.skipped`) and the run goes on. A step that runs something (an action, a read, a call or the "
    "assistant) may carry `on_error`: `stop` (none: the run stops with its reason) or `continue` (the failure is "
    "written in the step, later steps read `steps.<id>.failed` and `steps.<id>.error_code`, and the run goes on). "
    "A value in `params` is a literal, a path that keeps its type (`input.customer_id`) or text with "
    "`{{input.name}}` inside. Money is in cents."
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


class DueIn(In):
    pass


class DueOut(Schema):
    count: int


class DeletedOut(Schema):
    id: UUID
