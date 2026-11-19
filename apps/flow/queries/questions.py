"""The questions automations wait on (``flow.question.list`` and ``flow.question.get``, FLOW-F29), as «Waiting
for your answer» shows them to whoever may answer."""

import json
from typing import Any

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import NotFound, PermissionDenied
from live.operations import Operation, operation, registry

from apps.flow import recipes
from base import assistant as hub_assistant
from apps.flow.models import FlowRun, Question
from apps.flow.schemas import QuestionListIn, QuestionOut, QuestionPageOut, QuestionRefIn

from .pinned import pinned_values
from .reads import ANSWER, MANAGE, ROLE_PERMISSION, TURN
from .reasons import action_label

QUESTION_NOT_FOUND = _("That question does not exist in this business.")
QUESTION_NOT_YOURS = _("This question was asked of someone else: you cannot answer it.")
QUESTION_CLOSED = _("This question is closed: its automation no longer waits for it.")
#: The title of a change the assistant wants (FLOW-F38): kept when it is asked and said again, with its action, in the
#: language of whoever reads it (``question_row``).
ASSISTANT_WANTS = _("The assistant wants to change something in «%(app)s»")


def can_answer(ctx: OperationContext, role: str) -> bool:
    """Whether ``ctx`` may answer a question asked of ``role``: that role's people, and whoever runs the
    business, always."""
    return ctx.has(ROLE_PERMISSION.get(role, MANAGE)) or ctx.has(MANAGE)


def proposal_held(run: FlowRun) -> dict | None:
    """The change the assistant wants that ``run`` waits on (FLOW-F38, «Ask me first»), as its step keeps it, or
    ``None``: a run waits on one change at a time, the one its assistant step holds; an «Ask someone first» step has
    none."""
    steps = run.definition.get("steps") or []
    step = steps[run.step_index] if run.step_index < len(steps) else {}
    return (run.outputs.get(TURN) or {}).get("proposal") if step.get("kind") == "assistant" else None


def proposal_of(scope: Scope, question: Question) -> tuple[Operation, dict] | None:
    """The change the assistant wants that ``question`` waits on — its action and what a yes would send, with what its
    step fixes today put in (FLOW-F36: also a change proposed before its app fixed it) —, or ``None``: an «Ask someone
    first» question, or a change whose action is gone, has none (``proposal_held``)."""
    run = question.run
    proposal = proposal_held(run)
    op = registry.get(str(proposal.get("operation") or "")) if proposal else None
    if op is None:
        return None
    try:
        arguments = json.loads(proposal.get("arguments") or "{}")
    except ValueError:
        arguments = {}
    step = recipes.fixed_data(question.flow, run.definition["steps"])[run.step_index]
    fixed, empty = pinned_values(run, step, op.name)
    sent = {name: value for name, value in (arguments if isinstance(arguments, dict) else {}).items() if name not in empty}
    return op, {**sent, **fixed}


def question_row(ctx: OperationContext, question: Question) -> dict[str, Any]:
    """``question`` as «Waiting for your answer» shows it to ``ctx``'s person. A change the assistant wants is read
    now, as that person and in their language, never as the automation nor as it was kept: its title and its action
    as the History names it («Cancel a reservation»), and each datum as its confirmation card in the chat says it
    (BASE-F97 step 2), a record named only for whoever may read it, never by its id."""
    row = {
        "id": question.id,
        "flow_id": question.flow_id,
        "flow_name": question.flow.name,
        "run_id": question.run_id,
        "title": question.title,
        "details": question.details,
        "role": question.role,
        "on_no": question.on_no,
        "on_timeout": question.on_timeout,
        "expires_at": question.expires_at,
        "created_at": question.created_at,
        "action": "",
        "fields": [],
    }
    proposal = proposal_of(ctx.scope, question)
    if proposal is None:
        return row
    op, arguments = proposal
    with translation.override(ctx.language):
        title = str(ASSISTANT_WANTS) % {"app": hub_assistant.cards.app_name(op)}
        action = action_label(op, ctx.language)
    fields = hub_assistant.cards.card(op, arguments, ctx.language, ctx)["fields"]
    return row | {"title": title[:300], "action": action, "fields": fields}


@operation(
    "flow.question.list",
    kind="query",
    permission=ANSWER,
    input=QuestionListIn,
    output=QuestionPageOut,
    ai={
        "asks": {
            "en": (
                "what questions are the automations waiting for me to answer?",
                "is any automation waiting for my answer?",
            ),
            "es": (
                "¿qué preguntas de las automatizaciones tengo pendientes?",
                "¿alguna automatización espera mi respuesta?",
            ),
        },
        "description": "«Waiting for your answer»: the questions automations asked and are waiting on that this person may "
        "answer (their role's, or all of them for whoever runs the business), the soonest to expire first, "
        "up to 100."
    },
)
def list_questions(ctx: OperationContext, data: QuestionListIn) -> dict:
    roles = [role for role in ROLE_PERMISSION if can_answer(ctx, role)]
    pending = (
        Question.objects.select_related("flow", "run")
        .filter(status=Question.Status.PENDING, role__in=roles, run__status=FlowRun.Status.ASKING)
        .order_by("expires_at", "id")[:100]
    )
    return {"rows": [question_row(ctx, question) for question in pending]}


@operation(
    "flow.question.get",
    kind="query",
    permission=ANSWER,
    input=QuestionRefIn,
    output=QuestionOut,
    ai={
        "asks": {
            "en": (
                "show me that automation's question",
                "what exactly is the automation asking me?",
            ),
            "es": (
                "¿qué me pregunta exactamente la automatización?",
                "enséñame la pregunta que está esperando",
            ),
        },
        "description": "One question an automation asked and is waiting on, by its id, as «Waiting for your answer» "
        "shows it: what it asks, its details, the change of the assistant it waits on, if any, and until when. Only "
        "the role it was asked of, or whoever runs the business."
    },
)
def get_question(ctx: OperationContext, data: QuestionRefIn) -> dict:
    found = Question.objects.select_related("flow", "run").filter(pk=data.id).first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        if not can_answer(ctx, found.role):
            raise PermissionDenied(str(QUESTION_NOT_YOURS), code="flow.question_not_yours")
        if found.status != Question.Status.PENDING or found.run.status != FlowRun.Status.ASKING:
            raise NotFound(str(QUESTION_CLOSED), code="flow.question_closed")
    return question_row(ctx, found)
