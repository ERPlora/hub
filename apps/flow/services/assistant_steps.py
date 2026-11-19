"""The «Ask the assistant» steps (FLOW-F37 to F39): the worker asks the model a run's step with the
tools it was offered, runs what it asks for as the automation, and with «Ask me first» a change
waits for a person's yes."""

import datetime as dt
import json
import uuid
from typing import Any

from django.utils import timezone, translation
from live import assistant as shared
from live.context import OperationContext, Scope, system_context
from live.errors import OperationError
from live.operations import Operation, get, operation
from live.outbox import record_event

from apps.flow import document, events, gateway, recipes
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries import (
    ASSISTANT_GONE_KEY,
    SYSTEM,
    ask_first_catalog,
    catalog_operations,
    pinned_values,
    TURN,
    ASSISTANT_WANTS,
)
from apps.flow.schemas import (
    AssistantRoundIn,
    AssistantRoundOut,
    ClaimAssistantOut,
    DueOut,
    RecordAssistantIn,
    RunRefIn,
)
from base import assistant as hub_assistant, outbound

from .engine import _back_to_assistant, _call_failed, _end_turn, _fail, _finish, _go_on, _log, _own, _step_context
from .writes import CALL_LEASE_MINUTES

#: What the step's instructions add to the assistant's own: nobody is in front, and what a change does.
UNATTENDED = (
    "This is a step of the automation «%(name)s» and nobody is watching: never ask a question, decide with your "
    "tools and answer with what you found or did, in a few words."
)
#: What the assistant hears of a call of its answer that was not made: one change waits for a person at a time.
NOT_MADE = shared.error_content("not_made", "Not made: ask for one change at a time.")
#: What the assistant hears of a call whose fixed datum is empty in this run: the tool is not used (nothing half done).
PINNED_EMPTY_CODE = "flow.pinned_empty"
PINNED_EMPTY_TOLD = "Not made: %(fields)s, fixed by this step, is empty in this run, so this tool cannot be used now."
CHANGES = {
    "ask": "A change you ask for is not made yet: it waits for a person's yes, so say what you proposed.",
    "auto": "A change you ask for is made at once, for real.",
}


def _offered(ctx: OperationContext, flow: Flow, step: dict) -> dict[str, Operation]:
    """The tools of the step: what it names AND the automation was granted, of the active apps, that the assistant
    may use; never a person's permissions. Cancelling a booking (``ASK_FIRST``) only when it asks first."""
    catalog = ask_first_catalog(ctx.scope) if step.get("mode", "ask") == "ask" else catalog_operations(ctx.scope)
    tools: dict[str, Operation] = {}
    for name in step.get("tools") or []:
        op = catalog.get(name)
        if name in flow.grants and op is not None and hub_assistant.tools.is_tool(op):
            tools[name] = op
    return tools


def _spec(op: Operation, step: dict) -> dict:
    """``op`` as the step offers it to the assistant: without the data the step fixes, which it never sees."""
    spec = shared.tool_spec(op)
    fixed = (step.get("pinned") or {}).get(op.name)
    if not fixed:
        return spec
    parameters = dict(spec["parameters"])
    parameters["properties"] = {name: prop for name, prop in parameters.get("properties", {}).items() if name not in fixed}
    if "required" in parameters:
        parameters["required"] = [name for name in parameters["required"] if name not in fixed]
    return {**spec, "parameters": parameters}


def _pinned(run: FlowRun, step: dict, op: Operation) -> tuple[dict, list[str]]:
    """``(values, empty)``: the data the step fixes for ``op``, filled in with the run's data as its prompt is, and
    the names of those empty now (a path not found, a text with nothing in it)."""
    return pinned_values(run, step, op.name)


def _with_pinned(arguments: str, values: dict) -> str:
    """The model's ``arguments`` with the step's fixed data put in over whatever it sent for them; arguments that are
    no JSON object are left as they are (the tool refuses them before running)."""
    if not values:
        return arguments
    try:
        sent = json.loads(arguments or "{}")
    except ValueError:
        return arguments
    if not isinstance(sent, dict):
        return arguments
    return json.dumps({**sent, **values}, ensure_ascii=False)


def _instructions(ctx: OperationContext, flow: Flow, step: dict) -> str:
    try:
        business = get("base.business.get")(ctx, get("base.business.get").input()).model_dump()
    except OperationError:
        business = {}
    currency = business.get("currency") or "EUR"
    text = hub_assistant.prompt.instructions(
        language=flow.language,
        currency=currency,
        decimals=business.get("currency_decimals", 2),
        business=business.get("name") or "",
        screens={},
    )
    mode = CHANGES.get(step.get("mode", "ask"), CHANGES["ask"])
    return f"{text}\n\n{UNATTENDED % {'name': flow.name}} {mode}"


def _step_of(ctx: OperationContext, run: FlowRun, flow: Flow) -> dict:
    """The step ``run`` is on, as its automation was when it started, with the data its app fixes today (FLOW-F36):
    also a run started before its app fixed them."""
    return recipes.fixed_data(flow, run.definition["steps"])[run.step_index]


def _assistant_run(ctx: OperationContext, run_id: uuid.UUID) -> tuple[FlowRun | None, dict]:
    """The run whose «Ask the assistant» step is thinking, locked, and that step; ``None`` for any other."""
    run = FlowRun.objects.select_for_update(of=("self",)).select_related("flow").filter(pk=run_id).first()
    if run is None or run.status != FlowRun.Status.CALLING:
        return None, {}
    step = _step_of(ctx, run, run.flow)
    return (run, step) if step["kind"] == "assistant" else (None, {})


def dispatch_assistant(scope: Scope, run_id: uuid.UUID) -> None:
    """Asks the assistant a run's step, with no transaction and no lock around a turn: ``flow.run.claim_assistant`` →
    a turn → ``flow.run.assistant_round`` (its reads and actions, in a transaction of their own) → … →
    ``flow.run.record_assistant``. A step another process holds, or that ended meanwhile, is left alone."""
    system = system_context(scope)
    claimed = get("flow.run.claim_assistant")(system, RunRefIn(id=run_id))
    if not claimed.claimed:
        return
    messages, continuation = claimed.messages, claimed.continuation
    while True:
        outbound.release()  # each turn waits on the assistant with no connection held
        try:
            answer = gateway.turn(
                scope.key, messages=messages, tools=claimed.tools, instructions=claimed.instructions, continuation=continuation
            )
        except gateway.Failed as failed:
            get("flow.run.record_assistant")(system, RecordAssistantIn(id=run_id, failure=failed.code))
            return
        if not answer.calls:
            get("flow.run.record_assistant")(system, RecordAssistantIn(id=run_id, text=answer.text))
            return
        went = get("flow.run.assistant_round")(
            system,
            AssistantRoundIn(id=run_id, text=answer.text, calls=answer.calls, continuation=answer.continuation),
        )
        if not went.go_on:
            return
        messages, continuation = went.messages, went.continuation


def _due_calling_run(data: RunRefIn, now: dt.datetime) -> FlowRun | None:
    return (
        FlowRun.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("flow")
        .filter(pk=data.id, status=FlowRun.Status.CALLING, resume_at__lte=now)
        .first()
    )


@operation(
    "flow.run.claim_assistant",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=ClaimAssistantOut,
    ai={
        "description": "System only: takes a run's «Ask the assistant» step to ask it (nobody else holds it), with "
        "its task filled in, the tools it may use and its conversation so far, for CALL_LEASE_MINUTES.",
        "risk": "normal",
    },
)
def claim_assistant(ctx: OperationContext, data: RunRefIn) -> dict:
    now = timezone.now()
    run = _due_calling_run(data, now)
    if run is None:
        return {"claimed": False}
    flow = run.flow
    step = _step_of(ctx, run, flow)
    if step["kind"] != "assistant":
        return {"claimed": False}
    with translation.override(flow.language):
        if flow.deleted_at is not None:
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            return {"claimed": False}
        turn = run.outputs.get(TURN) or {
            "messages": [{"role": "user", "content": document.fill(step["prompt"], {"input": run.input, "steps": run.outputs})}],
            "rounds": 0,
            "continuation": None,
        }
        instructions = _instructions(ctx, flow, step)
    run.outputs = {**run.outputs, TURN: turn}
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save(update_fields=["outputs", "resume_at"])
    return {
        "claimed": True,
        "messages": turn["messages"],
        "tools": [_spec(op, step) for op in _offered(ctx, flow, step).values()],
        "instructions": instructions,
        "continuation": turn["continuation"],
    }


def _propose(  # noqa: PLR0913, PLR0917
    ctx: OperationContext,
    run: FlowRun,
    flow: Flow,
    step: dict,
    op: Operation,
    call: Any,
    arguments: str,
    later: list[str],
    turn: dict,
    said: str,
    now: dt.datetime,
) -> None:
    """«Ask me first»: the change waits in «Waiting for your answer» with what the assistant said, and the run on it;
    its title, its action and what it would send are said there for whoever reads it, as they read it
    (``queries.question_row``). A yes makes it (``answer_question``), a no or silence cancels the run, as a question
    that stops on a no. One change waits at a time: ``later``, the calls of the same answer behind it, are not made,
    and the assistant hears so with the change's result. Each change it asks for is a question of its own
    (``<step>:<n>``), so a late yes to one never approves the next."""
    question = Question.objects.create(
        run=run,
        flow=flow,
        step_id=f"{step['id']}:{Question.objects.filter(run=run).count() + 1}",
        title=(str(ASSISTANT_WANTS) % {"app": hub_assistant.cards.app_name(op)})[:300],
        details=said[:2000],
        role="",
        on_no="stop",
        on_timeout="no",
        expires_at=now + dt.timedelta(hours=72),
        created_at=now,
    )
    proposal = {"call_id": call.call_id, "operation": op.name, "arguments": arguments, "later": later}
    run.outputs = {**run.outputs, TURN: {**turn, "proposal": proposal}}
    _log(run, step, "assistant_proposed", now, operation=op.name, until=question.expires_at.isoformat())
    run.status = FlowRun.Status.ASKING
    run.resume_at = question.expires_at
    run.save()
    record_event(ctx, events.QUESTION_ASKED, {"id": str(question.id), "run_id": str(run.id), "flow_id": str(flow.id)})
    record_event(
        ctx, events.RUN_PARKED, {"id": str(run.id), "flow_id": str(flow.id), "resume_at": question.expires_at.isoformat()}
    )


@operation(
    "flow.run.assistant_round",
    kind="command",
    permission=SYSTEM,
    input=AssistantRoundIn,
    output=AssistantRoundOut,
    ai={
        "description": "System only: runs the reads and actions the assistant asked for in a run's step, as the "
        "automation and only those it was offered; with «Ask me first» a change waits for a person's yes instead.",
        "risk": "normal",
    },
)
def assistant_round(ctx: OperationContext, data: AssistantRoundIn) -> dict:
    now = timezone.now()
    run, step = _assistant_run(ctx, data.id)
    turn = run.outputs.get(TURN) if run is not None else None
    if run is None or turn is None:
        return {"go_on": False}
    flow = run.flow
    tools = _offered(ctx, flow, step)
    asked = [{"call_id": call.call_id, "name": call.name, "arguments": call.arguments} for call in data.calls]
    messages = [*turn["messages"], {"role": "assistant", "content": data.text, "tool_calls": [
        {"id": call["call_id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
        for call in asked
    ]}]
    with translation.override(flow.language):
        for index, call in enumerate(data.calls):
            op = shared.operation_of(call.name, tools)
            fixed, empty = _pinned(run, step, op) if op is not None else ({}, [])
            if op is None:
                content = shared.error_content("not_available", "That tool was not offered in this step.")
            elif empty:
                told = PINNED_EMPTY_TOLD % {"fields": ", ".join(f"«{name}»" for name in empty)}
                content = shared.error_content(PINNED_EMPTY_CODE, told)
                _log(run, step, "assistant_pinned_empty", now, operation=op.name, fields=empty)
            elif op.kind == "command" and step.get("mode", "ask") == "ask":
                later = [behind.call_id for behind in data.calls[index + 1 :]]
                asked_turn = {**turn, "messages": messages, "continuation": data.continuation}
                arguments = _with_pinned(call.arguments, fixed)
                _propose(ctx, run, flow, step, op, call, arguments, later, asked_turn, data.text, now)
                return {"go_on": False}
            else:
                outcome = shared.run_tool(_step_context(ctx, run, flow, op), op, _with_pinned(call.arguments, fixed))
                _log(run, step, "assistant_used", now, operation=op.name, ok=outcome.outcome == "ok")
                content = outcome.content
            messages.append({"role": "tool", "tool_call_id": call.call_id, "content": content})
        rounds = turn["rounds"] + 1
        if _out_of_rounds(ctx, run, flow, step, rounds, now):
            return {"go_on": False}
    run.outputs = {**run.outputs, TURN: {**turn, "messages": messages, "rounds": rounds, "continuation": data.continuation}}
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save()
    return {"go_on": True, "messages": messages, "continuation": data.continuation}


#: How a turn that did not come back ends: the gateway's code → ours (and the name of its reason).
_ASSISTANT_FAILURES = {
    "assistant.quota_exceeded": "flow.assistant_quota_exceeded",
    "assistant.unreachable": "flow.assistant_unreachable",
    "assistant.provider_unavailable": "flow.assistant_unavailable",
    "assistant.internal_error": "flow.assistant_unavailable",
    "assistant.unavailable": "flow.assistant_unavailable",
    "rate_limited": "flow.assistant_unavailable",
}


@operation(
    "flow.run.record_assistant",
    kind="command",
    permission=SYSTEM,
    input=RecordAssistantIn,
    output=DueOut,
    ai={
        "description": "System only: records what the assistant answered in a run's step, for the steps after it, "
        "and goes on (or stops the run with why it did not answer); an answer for a run no longer thinking changes nothing.",
        "risk": "normal",
    },
)
def record_assistant(ctx: OperationContext, data: RecordAssistantIn) -> dict:
    now = timezone.now()
    run, step = _assistant_run(ctx, data.id)
    if run is None:
        return {"count": 0}
    flow = run.flow
    answered = (run.outputs.get(TURN) or {}).get("answered") or {}
    _end_turn(run)
    with translation.override(flow.language):
        if data.failure:
            code = _ASSISTANT_FAILURES.get(data.failure, "flow.assistant_refused")
            _call_failed(ctx, run, flow, step, _own(code, technical=data.failure), now)
            return {"count": 1}
        run.outputs = {**run.outputs, step["id"]: {"text": data.text, **answered}}
        _log(run, step, "assistant_answered", now, text=data.text[:2000])
        run.step_index += 1
        _go_on(ctx, run, flow, now)
    return {"count": 1}


def _out_of_rounds(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, rounds: int, now: dt.datetime) -> bool:  # noqa: PLR0913, PLR0917
    """Stops the step when the assistant spent its turns (``max_rounds``) and says so; ``True`` when it did."""
    if rounds < int(step.get("max_rounds", 6)):
        return False
    _end_turn(run)
    failure = _own("flow.assistant_too_many_rounds", n=rounds)
    _call_failed(ctx, run, flow, step, failure, now)
    return True


def _make_proposal(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, answered: dict, now: dt.datetime) -> None:  # noqa: PLR0913, PLR0917
    """A yes to the assistant's change: it is made now, by its own operation, as the automation (what it was granted
    now, not when it was proposed), and the step goes back to the assistant with what happened — the change's result
    (or its refusal) and, for the calls of that answer behind it, that they were not made —, so it can say it or ask
    for the next change. The run goes on with what it answers then (``record_assistant``); a change no longer
    granted stops the step."""
    turn = run.outputs.get(TURN) or {}
    proposal = turn.get("proposal") or {}
    name = str(proposal.get("operation") or "")
    op = _offered(ctx, flow, step).get(name)
    if op is None:
        _end_turn(run)
        if _fail(ctx, run, step, _own("flow.not_allowed", ASSISTANT_GONE_KEY, operation=name), now):
            _go_on(ctx, run, flow, now)
        return
    # What the step fixes goes in again: a change proposed before its app fixed that datum is never made as the
    # assistant chose it (FLOW-F36), and one whose fixed datum is empty now is not made.
    fixed, empty = _pinned(run, step, op)
    if empty:
        told_empty = PINNED_EMPTY_TOLD % {"fields": ", ".join(f"«{name}»" for name in empty)}
        content = shared.error_content(PINNED_EMPTY_CODE, told_empty)
        _log(run, step, "assistant_pinned_empty", now, operation=op.name, fields=empty)
    else:
        arguments = _with_pinned(str(proposal.get("arguments") or "{}"), fixed)
        outcome = shared.run_tool(_step_context(ctx, run, flow, op), op, arguments)
        _log(run, step, "assistant_used", now, operation=op.name, ok=outcome.outcome == "ok")
        content = outcome.content
    told = [{"role": "tool", "tool_call_id": proposal["call_id"], "content": content}]
    told += [{"role": "tool", "tool_call_id": call_id, "content": NOT_MADE} for call_id in proposal.get("later") or []]
    rounds = turn["rounds"] + 1
    run.outputs = {
        **run.outputs,
        TURN: {
            **{key: value for key, value in turn.items() if key != "proposal"},
            "messages": [*turn["messages"], *told],
            "rounds": rounds,
            "answered": answered,
        },
    }
    if not _out_of_rounds(ctx, run, flow, step, rounds, now):
        _back_to_assistant(ctx, run, flow, step, now)
