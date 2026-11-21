"""The questions an «Ask someone first» step leaves (``flow.question.*``, FLOW-F28 to F30): answered by
a person, or closed when nobody answered in time."""

import datetime as dt

from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation
from live.outbox import record_event

from apps.flow import events
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries.catalog import grantable_operations, needs_a_person, yes_permission
from apps.flow.queries.questions import (
    QUESTION_CLOSED,
    QUESTION_NOT_FOUND,
    QUESTION_NOT_YOURS,
    can_answer,
    proposal_held,
)
from apps.flow.queries.reads import ANSWER, SYSTEM, TURN
from apps.flow.queries.reasons import action_label
from apps.flow.schemas.fields import DueIn, DueOut
from apps.flow.schemas.questions import AnsweredOut, AnswerIn

from .assistant_steps import _make_proposal, _step_of
from .engine import _finish, _go_on, _log, _own
from .writes import DISABLED, _actor

QUESTION_DECIDED = _("Someone already answered this one. Nothing was done twice.")
QUESTION_TOO_LATE = _("Too late: nobody answered it in time, so it was closed. Nothing was done.")
APPROVAL_BEYOND_YOU = _("Only someone who may do it themselves can say yes to «%(name)s».")


def _asked_for(run: FlowRun) -> dict[str, str]:
    """For the reason of a question nobody said yes to: the operation of the assistant's change it asked about, kept so
    the History names it by its action when it is read (``queries.reasons.say``); nothing for an «Ask someone first» one."""
    proposal = proposal_held(run)
    return {"operation": str(proposal["operation"])} if proposal and proposal.get("operation") else {}


def _who(ctx: OperationContext) -> str:
    """The name of whoever answers, as the history says it («Marta»)."""
    actor = ctx.actor
    if hasattr(actor, "get_username"):
        return (actor.get_full_name() or actor.get_username())[:128]
    return _actor(ctx)


def _carry_on(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, left: dict, now: dt.datetime) -> None:  # noqa: PLR0913, PLR0917
    run.outputs = {**run.outputs, step["id"]: left}
    run.step_index += 1
    _go_on(ctx, run, flow, now)


def _may_say_yes(ctx: OperationContext, run: FlowRun) -> None:
    """A yes to the assistant's change that needs a person in front (cancelling a booking, ``ASK_FIRST``) is only of
    someone who may make it themselves, whoever's it is (``yes_permission``): the yes lends nothing (the old engine's
    «no elevation»); the change still runs as the automation."""
    proposal = (run.outputs.get(TURN) or {}).get("proposal") or {}
    op = grantable_operations(ctx.scope).get(str(proposal.get("operation") or ""))
    if op is not None and needs_a_person(op) and not ctx.has(yes_permission(op)):
        message = str(APPROVAL_BEYOND_YOU) % {"name": action_label(op, ctx.language)}
        raise PermissionDenied(message, code="flow.approval_beyond_you")


@operation(
    "flow.question.answer",
    kind="command",
    permission=ANSWER,
    input=AnswerIn,
    output=AnsweredOut,
    ai={
        "asks": {
            "en": (
                "answer yes to the automation's question",
                "say no to that question, the customer already paid",
            ),
            "es": (
                "dile que sí a la automatización que espera mi respuesta",
                "responde que no a la automatización de impagos, el cliente ya ha pagado",
            ),
        },
        "description": "Answer yes or no, with an optional note, to a question an automation asked and is waiting "
        "on (from `flow.question.list`): a yes carries it on, a no does what its step says. Only the role it was "
        "asked of, or whoever runs the business. The yes or the no is the one the person said, never your own.",
        "risk": "high",
    },
)
def answer_question(ctx: OperationContext, data: AnswerIn) -> dict:
    now = timezone.now()
    found = Question.objects.filter(pk=data.id).values_list("flow_id", "run_id").first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        # The order of every write: the automation, then its run, then the question.
        flow = Flow.objects.select_for_update().filter(pk=found[0]).first()
        run = FlowRun.objects.select_for_update().filter(pk=found[1]).first()
        question = Question.objects.select_for_update().filter(pk=data.id).first()
        if flow is None or run is None or question is None:
            raise NotFound(str(QUESTION_NOT_FOUND), code="flow.question_not_found")
        if not can_answer(ctx, question.role):
            raise PermissionDenied(str(QUESTION_NOT_YOURS), code="flow.question_not_yours")
        pending = question.status == Question.Status.PENDING
        if question.status == Question.Status.EXPIRED or (pending and question.expires_at <= now):
            raise Conflict(str(QUESTION_TOO_LATE), code="flow.question_expired")
        if not pending or run.status != FlowRun.Status.ASKING:
            closed = question.status == Question.Status.CANCELLED or run.status != FlowRun.Status.ASKING
            raise Conflict(str(QUESTION_CLOSED if closed else QUESTION_DECIDED), code="flow.question_decided")
        goes_on = data.approve or question.on_no == "continue"
        if goes_on and not flow.enabled:
            raise Conflict(str(DISABLED), code="flow.disabled")
        if data.approve:
            _may_say_yes(ctx, run)
    who = _who(ctx)
    question.status = Question.Status.APPROVED if data.approve else Question.Status.REJECTED
    question.decided_by, question.decided_at, question.note = who, now, data.note
    question.save(update_fields=["status", "decided_by", "decided_at", "note"])
    record_event(ctx, events.QUESTION_ANSWERED, {"id": str(question.id), "run_id": str(run.id)})
    step = _step_of(ctx, run, flow)
    with translation.override(flow.language):
        _log(run, step, "answered", now, approved=data.approve, by=who, note=data.note)
        if goes_on and step["kind"] == "assistant":
            _make_proposal(ctx, run, flow, step, {"approved": True, "note": data.note, "answered_by": who}, now)
        elif goes_on:
            left = {"approved": data.approve, "expired": False, "note": data.note, "answered_by": who}
            _carry_on(ctx, run, flow, step, left, now)
        else:
            no = _own("flow.question_rejected", who=who, title=question.title, **_asked_for(run))
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, no)
    return {"id": question.id, "run_id": run.id, "status": run.status}


@operation(
    "flow.question.expire_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "System only, every minute: closes the questions nobody answered in time and does what "
        "each step says for silence (what a no does, stop, or carry on).",
        "risk": "normal",
    },
)
def expire_questions(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    # The run first, with SKIP LOCKED: one being answered (its automation and run locked) is left to it.
    due = (
        FlowRun.objects.filter(status=FlowRun.Status.ASKING, resume_at__lte=now)
        .select_related("flow")
        .select_for_update(skip_locked=True, of=("self",))
        .order_by("resume_at", "id")
    )
    closed = 0
    for run in due:
        flow = run.flow
        step = run.definition["steps"][run.step_index]
        # The one it waits on: an «Ask someone first» step's own, or the assistant's last change (``<step>:<n>``).
        question = Question.objects.select_for_update().filter(run=run, status=Question.Status.PENDING).first()
        if question is None:
            continue
        question.status, question.decided_at = Question.Status.EXPIRED, now
        question.save(update_fields=["status", "decided_at"])
        record_event(ctx, events.QUESTION_EXPIRED, {"id": str(question.id), "run_id": str(run.id)})
        closed += 1
        policy = question.on_no if question.on_timeout == "no" else question.on_timeout
        with translation.override(flow.language):
            _log(run, step, "expired", now)
            if policy != "continue":
                silence = _own("flow.question_expired", title=question.title, **_asked_for(run))
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, silence)
            elif flow.deleted_at is not None:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            elif not flow.enabled:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.paused"))
            else:
                left = {"approved": False, "expired": True, "note": "", "answered_by": ""}
                _carry_on(ctx, run, flow, step, left, now)
    return {"count": closed}
