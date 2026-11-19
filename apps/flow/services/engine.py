"""The engine that runs an automation's steps: a run starts, goes through its steps in order, each one an
operation of another app nested in a savepoint, and ends, fails or parks: on a delay, on a call to
another system (FLOW-F27), on a question to someone (FLOW-F28) or on the assistant (FLOW-F37)."""

import datetime as dt
import json
import logging
import re
from typing import Any

import pydantic
from django.utils import translation
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import Operation
from live.outbox import record_event

from apps.flow import document, events
from apps.flow.apps import RUN_ACTOR
from apps.flow.models import Flow, FlowRun, Question
from apps.flow.queries.catalog import catalog_operations, grantable_operations, needs_a_person, read_permissions
from apps.flow.queries.problems import HIGH_RISK_CODE
from apps.flow.queries.reads import TURN
from apps.flow.queries.reasons import say
from apps.flow.queries.runs import LEAVES
from apps.flow.queries.values import map_params, prepared, validation_fields, PERSON_PARAMS, words_for

from .writes import _actor

logger = logging.getLogger(__name__)


class StepFailed(Exception):
    """Why a step (or a run) stopped: ``message`` in the automation's language, for the steps after it; ``reason``,
    the engine's own reason by name and values (``_own``), said again when the History is read, in the reader's
    language; none for what an action of another app answered, which is said as it answered."""

    def __init__(
        self,
        code: str,
        message: str,
        fields: dict | None = None,
        technical: str = "",
        reason: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.fields, self.technical, self.reason = (
            code,
            message,
            fields,
            technical,
            reason or {},
        )

    def entry(self) -> dict:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        if self.technical:
            error["technical"] = self.technical
        if self.reason:
            error["reason"] = self.reason
        return error


def _own(code: str, key: str = "", *, fields: dict | None = None, technical: str = "", **values: Any) -> StepFailed:
    """A failure in the engine's own words (``queries.reasons.REASONS[key or code]``), said now in the active language (the
    automation's) and kept by name and values for whoever reads it later."""
    reason = {"key": key or code, "values": values}
    return StepFailed(code, say(reason), fields=fields, technical=technical, reason=reason)


def _log(run: FlowRun, step: dict, outcome: str, now: dt.datetime, **more: Any) -> None:
    entry = {"step": step["id"], "kind": step["kind"]}
    if step.get("operation"):
        entry["operation"] = step["operation"]
    run.log = [*run.log, {**entry, "outcome": outcome, **more, "at": now.isoformat()}]


#: An id as the records of the Hub write it (UUIDv7, as text).
ANY_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _remember_read(run: FlowRun) -> None:
    """Keeps the ids in what ``run``'s steps left (a customer's card, a sale…), never their data, before that is
    forgotten: erasing a customer finds by them a run whose texts may name her once it no longer keeps her card."""
    found = ANY_ID.findall(json.dumps(run.outputs, default=str))
    run.read_ids = sorted({*run.read_ids, *found})


def _end_turn(run: FlowRun) -> None:
    """The assistant's turn is over: what it was told (what its tools read) goes, its ids are kept."""
    _remember_read(run)
    run.outputs = {key: value for key, value in run.outputs.items() if key != TURN}


def _start(  # noqa: PLR0913
    ctx: OperationContext,
    flow: Flow,
    *,
    kind: str,
    key: str,
    input: dict,
    now: dt.datetime,
    event_name: str = "",
    chain: list[str] | None = None,
) -> FlowRun:
    started = FlowRun.objects.create(
        flow=flow,
        flow_version=flow.version,
        definition={"steps": flow.steps},
        trigger_kind=kind,
        trigger_key=key,
        event_name=event_name,
        input=input,
        chain=chain or [],
        started_by=_actor(ctx),
        started_at=now,
    )
    record_event(
        ctx, events.RUN_STARTED, {"id": str(started.id), "flow_id": str(flow.id)}
    )
    return started


def _finish(
    ctx: OperationContext,
    run: FlowRun,
    status: str,
    now: dt.datetime,
    failure: StepFailed | None = None,
) -> None:
    run.status = status
    run.finished_at = now
    run.resume_at = None
    # What the steps read (a customer's card…) is only needed while the run may go on: none is kept,
    # except by one that stopped by an error, which may be resumed for RESUME_DAYS (FLOW-F24); its ids are.
    _remember_read(run)
    if status != FlowRun.Status.FAILED:
        run.outputs = {}
    run.error_code = failure.code if failure else ""
    run.error_message = failure.message if failure else ""
    run.error_reason = failure.reason if failure else {}
    run.save()
    record_event(
        ctx,
        events.RUN_FINISHED,
        {"id": str(run.id), "flow_id": str(run.flow_id), "status": status},
    )


def _step_context(ctx: OperationContext, run: FlowRun, flow: Flow, op: Operation) -> OperationContext:
    """What a step runs with: the run's reference as the actor, the permission of its own operation and
    the reads of its app (to answer with what it did), never every permission — the operation's own
    checks still apply (the old engine's «no elevation») —, in the language of whoever saved it."""
    return OperationContext(
        scope=ctx.scope,
        actor=f"{RUN_ACTOR}{run.id}",
        permissions=frozenset({op.permission}) | read_permissions(ctx.scope, op),
        language=flow.language,
    )


def _read_output(step: dict, output: dict) -> tuple[dict, str, int]:
    """``(what the step leaves, outcome, count)`` of a read: the first row's fields (or none) and found/count."""
    if "rows" in output and isinstance(output["rows"], list):
        rows = output["rows"]
        count = int(output.get("total", len(rows)))
        first = rows[0] if rows and isinstance(rows[0], dict) else {}
    else:
        count, first = 1, output
    found = count > 0
    left = (dict(first) if step.get("result", "first") == "first" else {}) | {
        "found": found,
        "count": count,
    }
    return left, "found" if found else "not_found", count


def _operation_step(
    ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, data: dict
) -> tuple[dict, str, dict]:
    """Runs a command or query step; ``(what it leaves, outcome, log extras)`` or ``StepFailed``."""
    name = step["operation"]
    grantable = grantable_operations(ctx.scope).get(name)
    if grantable is not None and needs_a_person(grantable):
        raise _own(HIGH_RISK_CODE, name=name)
    if name not in flow.grants:
        raise _own("flow.not_allowed", name=name)
    op = catalog_operations(ctx.scope).get(name)
    if op is None or op.kind != step["kind"]:
        raise _own("flow.action_unavailable", name=name)
    step_ctx = _step_context(ctx, run, flow, op)
    say = words_for(run.definition["steps"], flow.language, ctx.scope, data)
    values, _, _ = map_params(step.get("params", {}), data, say=say, person=PERSON_PARAMS.get(name, ()))
    try:
        payload = op.input.model_validate(
            prepared(op, step["kind"], step.get("result", "first"), values)
        )
    except pydantic.ValidationError as invalid:
        raise _own("flow.invalid_params", fields=validation_fields(invalid), name=name) from None
    try:
        result = op(step_ctx, payload)
    except NotFound:
        if step["kind"] == "query":
            return {"found": False, "count": 0}, "not_found", {"count": 0}
        raise
    except OperationError as refused:
        raise StepFailed(refused.code, refused.message, fields=refused.fields) from None
    except Exception as crash:
        logger.exception(
            "flow: step %s (%s) of run %s crashed", step["id"], name, step_ctx.actor
        )
        raise _own("flow.step_crashed", technical=f"{type(crash).__name__}: {crash}", name=name) from None
    output = result.model_dump(mode="json")
    if step["kind"] == "query":
        left, outcome, count = _read_output(step, output)
        return left, outcome, {"count": count}
    return output, "done", {}


def _fail(  # noqa: PLR0913, PLR0917
    ctx: OperationContext, run: FlowRun, step: dict, failure: StepFailed, now: dt.datetime, left: dict | None = None
) -> bool:
    """Writes a step's failure; ``True`` when the run goes on (``on_error: continue``, FLOW-F25), leaving
    ``failed``, ``error_code``, ``error_message`` and ``left`` (a call's ``status``) for later steps."""
    if step.get("on_error") == "continue":
        _log(run, step, "failed", now, error=failure.entry(), continued=True)
        run.outputs = {
            **run.outputs,
            step["id"]: {"failed": True, "error_code": failure.code, "error_message": failure.message, **(left or {})},
        }
        run.step_index += 1
        return True
    _log(run, step, "failed", now, error=failure.entry())
    _finish(ctx, run, FlowRun.Status.FAILED, now, failure)
    return False


def _skipped(ctx: OperationContext, run: FlowRun, step: dict, data: dict, now: dt.datetime) -> bool | None:
    """Applies a step's «Only if…» (FLOW-F25): ``True`` when it is skipped (and the run goes on),
    ``None`` when it cannot be read (the run stopped), ``False`` when the step runs."""
    run_if = step.get("run_if")
    if not run_if:
        return False
    if not document.readable(run_if):
        _fail(ctx, run, {**step, "on_error": "stop"}, _own("flow.run_if_unreadable"), now)
        return None
    failed = document.failed_clauses(run_if, data)
    if not failed:
        return False
    _log(run, step, "skipped", now, failed=failed)
    if step["kind"] in LEAVES:
        run.outputs = {**run.outputs, step["id"]: {"skipped": True}}
    run.step_index += 1
    return True


def _advance(ctx: OperationContext, run: FlowRun, flow: Flow, now: dt.datetime) -> None:  # noqa: C901, PLR0911, PLR0912
    """Runs ``run``'s steps from ``step_index`` until it ends, waits or fails."""
    steps = run.definition.get("steps", [])
    with translation.override(flow.language):
        while run.step_index < len(steps):
            step = steps[run.step_index]
            data = {"input": run.input, "steps": run.outputs}
            if step["kind"] != "condition":
                skipped = _skipped(ctx, run, step, data, now)
                if skipped is None:
                    return
                if skipped:
                    continue
            if step["kind"] == "delay":
                until = now + dt.timedelta(seconds=step["seconds"])
                _log(
                    run,
                    step,
                    "waiting",
                    now,
                    seconds=step["seconds"],
                    until=until.isoformat(),
                )
                run.step_index += 1
                run.status = FlowRun.Status.WAITING
                run.resume_at = until
                run.save()
                record_event(
                    ctx,
                    events.RUN_PARKED,
                    {
                        "id": str(run.id),
                        "flow_id": str(flow.id),
                        "resume_at": until.isoformat(),
                    },
                )
                return
            if step["kind"] == "condition":
                if not document.readable(step.get("when")):
                    failure = _own("flow.condition_unreadable")
                    _fail(ctx, run, {**step, "on_error": "stop"}, failure, now)
                    return
                failed = document.failed_clauses(step["when"], data)
                if failed:
                    _log(run, step, "stopped", now, failed=failed)
                    _finish(ctx, run, FlowRun.Status.STOPPED, now)
                    return
                _log(run, step, "passed", now)
                run.step_index += 1
                continue
            if step["kind"] == "http":
                if _park_call(ctx, run, flow, step, now):
                    return
                continue
            if step["kind"] == "ask":
                _ask(ctx, run, flow, step, data, now)
                return
            if step["kind"] == "assistant":
                _park_assistant(ctx, run, flow, step, now)
                return
            try:
                left, outcome, extras = _operation_step(ctx, run, flow, step, data)
            except StepFailed as failure:
                if _fail(ctx, run, step, failure, now):
                    continue
                return
            except OperationError as refused:
                if _fail(ctx, run, step, StepFailed(refused.code, refused.message), now):
                    continue
                return
            run.outputs = {**run.outputs, step["id"]: left}
            _log(run, step, outcome, now, **extras)
            run.step_index += 1
        _finish(ctx, run, FlowRun.Status.SUCCEEDED, now)


def _call_allowed(run: FlowRun, flow: Flow, step: dict) -> StepFailed | None:
    """Why the automation may not make this call (its origin not granted), or ``None``."""
    grant = document.http_grant(str(step.get("url") or ""))
    if grant is None:
        return _own("flow.http_url_invalid")
    if grant not in flow.grants:
        return _own("flow.not_allowed", name=document.host_of(step["url"]))
    return None


def _mark_calling(  # noqa: PLR0913, PLR0917
    ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, outcome: str, now: dt.datetime, **details
) -> None:
    _log(run, step, outcome, now, **details)
    run.status = FlowRun.Status.CALLING
    run.resume_at = now
    run.save()
    record_event(
        ctx, events.RUN_PARKED, {"id": str(run.id), "flow_id": str(flow.id), "resume_at": now.isoformat()}
    )


def _park_call(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> bool:
    """Parks the run on a call and answers: the call never goes out from here (a web request would wait for
    the other system). Its ``flow.run.parked`` reaches the worker through the outbox relay, which makes it
    (``flow.run.call``); ``True`` when the run stops here (parked, or failed), ``False`` when it goes on (a
    refusal with «If it fails, carry on»)."""
    refused = _call_allowed(run, flow, step)
    if refused is not None:
        return not _fail(ctx, run, step, refused, now)
    _mark_calling(ctx, run, flow, step, "calling", now, host=document.host_of(step["url"]))
    return True


def _go_on(ctx: OperationContext, run: FlowRun, flow: Flow, now: dt.datetime) -> None:
    run.status = FlowRun.Status.RUNNING
    run.resume_at = None
    record_event(ctx, events.RUN_RESUMED, {"id": str(run.id), "flow_id": str(flow.id)})
    _advance(ctx, run, flow, now)


def _call_failed(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, failure: StepFailed, now, left=None) -> None:  # noqa: PLR0913, PLR0917
    run.resume_at = None
    if _fail(ctx, run, step, failure, now, left):
        _go_on(ctx, run, flow, now)


def _park_assistant(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> None:
    """Parks the run on its «Ask the assistant» step and answers: the model is never asked from here (a web request
    would wait for it). Its ``flow.run.parked`` reaches the worker, which asks it (``flow.run.call``); a step resumed
    (FLOW-F24) starts its conversation again."""
    _end_turn(run)
    _back_to_assistant(ctx, run, flow, step, now)


def _back_to_assistant(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, now: dt.datetime) -> None:
    """Parks the run for the worker to ask the assistant, with the step's conversation as it is."""
    _mark_calling(ctx, run, flow, step, "thinking", now)


def _ask(ctx: OperationContext, run: FlowRun, flow: Flow, step: dict, data: dict, now: dt.datetime) -> None:  # noqa: PLR0913, PLR0917
    """Leaves the step's question, its texts filled in now, in «Waiting for your answer» and parks the run on it. A
    question the run already asked at this step (a run resumed onto it) is not asked twice."""
    expires = now + dt.timedelta(hours=int(step.get("hours", 72)))
    # Its texts are read by a person: each datum in words, in the language of whoever saved the automation.
    say = words_for(run.definition["steps"], flow.language, ctx.scope, data)
    question, _created = Question.objects.get_or_create(
        run=run,
        step_id=step["id"],
        defaults={
            "flow": flow,
            "title": document.fill(step["title"], data, say)[:300],
            "details": document.fill(step.get("details", ""), data, say),
            "role": step.get("role", ""),
            "on_no": step.get("on_no", "stop"),
            "on_timeout": step.get("on_timeout", "no"),
            "expires_at": expires,
            "created_at": now,
        },
    )
    _log(run, step, "asking", now, role=question.role, until=question.expires_at.isoformat())
    run.status = FlowRun.Status.ASKING
    run.resume_at = question.expires_at
    run.save()
    record_event(
        ctx, events.QUESTION_ASKED, {"id": str(question.id), "run_id": str(run.id), "flow_id": str(flow.id)}
    )
    record_event(
        ctx,
        events.RUN_PARKED,
        {"id": str(run.id), "flow_id": str(flow.id), "resume_at": question.expires_at.isoformat()},
    )
