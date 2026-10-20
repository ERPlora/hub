"""Write operations of the flow app, and the engine that runs the automations.

One operation = one transaction, with its events in the outbox. A write on an automation locks its row
(``select_for_update``) before it looks at it, so two saves, or a save and a run, wait for each other.
What a document names (an event, an action, a read) is checked against the active apps
(``queries.catalog_problems``) and refused by field; nothing fails in silence.

**The engine.** A run starts in ``flow.run.react`` (an event of another app), ``flow.schedule.fire_due``
(a schedule or a date), ``flow.flow.run`` (by hand) and goes on in ``flow.run.resume_due`` (after a
wait). Its steps run in order, in the same transaction, each one an operation of another app nested in
a savepoint: a step that fails leaves nothing of its own and stops the run with its reason; the steps
before it stay. A step runs only if the automation was granted its operation, with the context
``flow_run:<id>`` (what it does carries that reference in the outbox) and the system's permissions,
in the language of whoever saved the automation. One run per automation and trigger key (the outbox
event's id): the row lock and the unique constraint make a repeated delivery start nothing. A run
started by an event that a run of the same automation caused, or by a chain of more than
``document.MAX_CHAIN`` automations, stops before doing anything (``flow.loop_stopped``).
"""

import datetime as dt
import logging
import uuid
from typing import Any

import pydantic
from django.db.models.functions import Coalesce
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import Operation, operation
from live.outbox import record_event

from apps.flow import document, events
from apps.flow.models import Draft, Flow, FlowRun
from apps.flow.queries import (
    HIGH_RISK,
    HIGH_RISK_CODE,
    MANAGE,
    RESUME_DAYS,
    SYSTEM,
    catalog_operations,
    catalog_problems,
    grantable_operations,
    needs_a_person,
    operation_problem,
    read_permissions,
    resume_problem,
    draft_row,
    flow_row,
    live_flows,
    map_params,
    prepared,
    resolve_flow,
    run_row,
    validation_fields,
)
from apps.flow.schemas import (
    CreateIn,
    DeletedOut,
    DraftOut,
    DraftProposeIn,
    DraftRefIn,
    DueIn,
    DueOut,
    EnabledIn,
    FlowOut,
    FlowRefIn,
    GrantIn,
    ReactIn,
    ReactOut,
    RunIn,
    RunOut,
    RunRefIn,
    UpdateIn,
)

logger = logging.getLogger(__name__)

UNTITLED = _("Untitled automation")
COPY_OF = _("Copy of %(name)s")
NUMBERED = "%(name)s (%(n)s)"
PAST_DATE = _("That date and time has already passed.")
DISABLED = _("This automation is paused: turn it on to run it.")
DRAFT_DECIDED = _("That draft was already decided.")
GRANT_BEYOND_CALLER = _("You cannot allow what you may not do yourself: «%(name)s».")
DRAFT_NOT_FOUND = _("That draft does not exist in this business.")
NOT_ALLOWED = _(
    "It tried to do something you have not allowed it to do («%(name)s»), so it stopped. "
    "Open Permissions and allow what it needs."
)
UNAVAILABLE = _(
    "«%(name)s» is not available in this business any more (its app is off), so it stopped."
)
INVALID_PARAMS = _("«%(name)s» did not accept the data it was given, so it stopped.")
CRASHED = _(
    "Something went wrong while doing «%(name)s», so it stopped. Nothing of that step was kept."
)
LOOP = _(
    "It was started by something its own steps did, so it stopped before doing anything."
)
CHAIN_TOO_LONG = _(
    "A chain of %(count)s automations started it, more than the %(max)s allowed, so it stopped before doing "
    "anything."
)
FILTER_UNREADABLE = _(
    "Its «Only when…» can no longer be read, so it did not go on. Open it, check «Only when…» and save it "
    "again."
)
CONDITION_UNREADABLE = _(
    "This «Only continue if…» can no longer be read, so it stopped. Open the automation, check this step "
    "and save it again."
)
CANCELLED_PAUSED = _("Cancelled: the automation was paused while it waited.")
CANCELLED_DELETED = _("Cancelled: the automation was deleted.")
RUN_NOT_FOUND = _("That run does not exist in this business.")

#: How long the history keeps a finished run (hub#699: the old Hub's 90 days, fixed, for every hub).
HISTORY_DAYS = 90
#: At most this many runs go per pass: bounded, never one mass delete at the busiest hour.
PRUNE_BATCH = 500
#: The runs that can no longer go on: what the history may forget (waiting and running ones never).
FINISHED = (
    FlowRun.Status.SUCCEEDED,
    FlowRun.Status.STOPPED,
    FlowRun.Status.FAILED,
    FlowRun.Status.CANCELLED,
)

#: The actor prefix of what a run does (``flow_run:<id>``): the outbox keeps it, the loop guard reads it.
RUN_ACTOR = "flow_run:"


def _actor(ctx: OperationContext) -> str:
    return "" if ctx.actor is None else str(ctx.actor)[:128]


def _business_zone() -> dt.tzinfo:
    """The business's time zone (phase 1: ``settings.TIME_ZONE``, Europe/Madrid)."""
    return timezone.get_default_timezone()


# --- The document on an automation ------------------------------------------------------------------


def refresh_search_text(flow: Flow) -> None:
    """What the list's search looks in: the name, the event and the operations of its steps."""
    parts = [flow.name, flow.trigger_event, *document.required_grants(flow.steps)]
    flow.search_text = " ".join(part for part in parts if part)


def _apply_trigger(flow: Flow, trigger: Any) -> None:
    flow.trigger_kind = trigger.kind
    flow.trigger_event = trigger.event if trigger.kind == "event" else ""
    flow.trigger_filter = trigger.filter if trigger.kind == "event" else {}
    flow.schedule = (
        {
            key: value
            for key, value in trigger.model_dump(mode="json").items()
            if key != "kind"
        }
        if trigger.kind == "schedule"
        else {}
    )
    flow.run_at = trigger.at if trigger.kind == "at" else None


def _check(trigger: Any, steps: list[Any] | None, now: dt.datetime, saved_at: dt.datetime | None = None) -> None:
    """Refuses, by field, what this business does not have and a date that has passed — only a date that
    changes (``saved_at`` is the one it keeps): one that already went off must not block a rename."""
    problems, code = catalog_problems(trigger, steps or [])
    if trigger is not None and trigger.kind == "at" and trigger.at != saved_at and trigger.at <= now:
        problems["trigger.at"] = str(PAST_DATE)
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)


def _next_fire(flow: Flow, now: dt.datetime) -> dt.datetime | None:
    """When a schedule or a date starts it next, counted from ``now``; ``None`` while it never will."""
    if not flow.enabled:
        return None
    if flow.trigger_kind == Flow.Trigger.SCHEDULE:
        return document.next_fire(flow.schedule, now, _business_zone())
    if flow.trigger_kind == Flow.Trigger.AT and flow.run_at and flow.run_at > now:
        return flow.run_at
    return None


def _record_switch(ctx: OperationContext, flow: Flow) -> None:
    record_event(
        ctx,
        events.FLOW_ENABLED if flow.enabled else events.FLOW_PAUSED,
        {"id": str(flow.id)},
    )


# --- Create, change, switch, copy, delete -----------------------------------------------------------


def _decide_draft(
    ctx: OperationContext, draft_id, status: str, flow: Flow | None = None
) -> Draft:
    draft = Draft.objects.select_for_update().filter(pk=draft_id).first()
    if draft is None:
        raise NotFound(str(DRAFT_NOT_FOUND))
    if draft.status != Draft.Status.PENDING:
        raise Conflict(str(DRAFT_DECIDED), code="flow.draft_decided")
    draft.status = status
    draft.flow = flow
    draft.decided_by = _actor(ctx)
    draft.decided_at = timezone.now()
    draft.save(update_fields=["status", "flow", "decided_by", "decided_at"])
    return draft


@operation(
    "flow.flow.create",
    kind="command",
    permission=MANAGE,
    input=CreateIn,
    output=FlowOut,
    ai={
        "description": "Create an automation from scratch, from a gallery card or from the assistant's draft "
        "(`draft_id`, which is marked as used in the same step). It is born paused and with no permission "
        "(`flow.flow.set_enabled` turns it on); prefer `flow.draft.propose` when somebody asks you for one.",
        "risk": "normal",
    },
)
def create_flow(ctx: OperationContext, data: CreateIn) -> dict:
    now = timezone.now()
    _check(data.trigger, data.steps, now)
    with translation.override(ctx.language):
        name = data.name or str(UNTITLED)
    flow = Flow(
        name=name,
        steps=[step.model_dump(mode="json") for step in data.steps],
        language=ctx.language,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    _apply_trigger(flow, data.trigger)
    flow.next_fire_at = _next_fire(flow, now)
    refresh_search_text(flow)
    flow.save()
    record_event(ctx, events.FLOW_CREATED, {"id": str(flow.id)})
    if data.draft_id is not None:
        draft = _decide_draft(ctx, data.draft_id, Draft.Status.USED, flow)
        record_event(
            ctx, events.DRAFT_USED, {"id": str(draft.id), "flow_id": str(flow.id)}
        )
    return flow_row(flow)


@operation(
    "flow.flow.update",
    kind="command",
    permission=MANAGE,
    input=UpdateIn,
    output=FlowOut,
    ai={
        "description": "Change an automation, by its id or its name: its name, what starts it or its steps (to turn "
        "it on or pause it, `flow.flow.set_enabled`). Only what is sent changes; its permissions stay. Changing the trigger or the steps "
        "raises its version, and what is already running goes on with the version it started with.",
        "risk": "normal",
    },
)
def update_flow(ctx: OperationContext, data: UpdateIn) -> dict:
    now = timezone.now()
    flow = resolve_flow(data.id, data.flow, lock=True)
    _check(data.trigger, data.steps, now, saved_at=flow.run_at)
    changed_document = False
    if data.name is not None:
        with translation.override(ctx.language):
            flow.name = data.name or str(UNTITLED)
    if data.trigger is not None:
        before = (
            flow.trigger_kind,
            flow.trigger_event,
            flow.trigger_filter,
            flow.schedule,
            flow.run_at,
        )
        _apply_trigger(flow, data.trigger)
        changed_trigger = before != (
            flow.trigger_kind,
            flow.trigger_event,
            flow.trigger_filter,
            flow.schedule,
            flow.run_at,
        )
        changed_document |= changed_trigger
    else:
        changed_trigger = False
    if data.steps is not None:
        steps = [step.model_dump(mode="json") for step in data.steps]
        changed_document |= steps != flow.steps
        flow.steps = steps
    if changed_document:
        flow.version += 1
    if changed_trigger:
        flow.next_fire_at = _next_fire(flow, now)
    flow.language = ctx.language
    flow.updated_by = _actor(ctx)
    refresh_search_text(flow)
    flow.save()
    if changed_document or data.name is not None:
        record_event(
            ctx, events.FLOW_UPDATED, {"id": str(flow.id), "version": flow.version}
        )
    return flow_row(flow)


@operation(
    "flow.flow.set_enabled",
    kind="command",
    permission=MANAGE,
    input=EnabledIn,
    output=FlowOut,
    ai={
        "description": "Turn an automation on or pause it, by its id or its name («activate the welcome "
        "automation», «pause the cash close one»). A schedule turned on counts from now. Turning on one that "
        "lacks permissions leaves it doing nothing until they are granted: say so.",
        "risk": "high",
    },
)
def set_enabled(ctx: OperationContext, data: EnabledIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    if flow.enabled != data.enabled:
        flow.enabled = data.enabled
        flow.next_fire_at = _next_fire(flow, timezone.now())
        flow.updated_by = _actor(ctx)
        flow.save(update_fields=["enabled", "next_fire_at", "updated_by", "updated_at"])
        _record_switch(ctx, flow)
    return flow_row(flow)


@operation(
    "flow.flow.duplicate",
    kind="command",
    permission=MANAGE,
    input=FlowRefIn,
    output=FlowOut,
    ai={
        "description": "Copy an automation: «Copy of …», paused, with the same trigger and steps and none of its "
        "permissions or history.",
        "risk": "normal",
    },
)
def duplicate_flow(ctx: OperationContext, data: FlowRefIn) -> dict:
    original = resolve_flow(data.id, data.flow)
    with translation.override(ctx.language):
        base = str(COPY_OF) % {"name": original.name}
    taken = set(
        live_flows().filter(name__startswith=base).values_list("name", flat=True)
    )
    name, n = base, 2
    while name in taken:
        name, n = NUMBERED % {"name": base, "n": n}, n + 1
    copy = Flow(
        name=name[: Flow._meta.get_field("name").max_length],
        enabled=False,
        trigger_kind=original.trigger_kind,
        trigger_event=original.trigger_event,
        trigger_filter=original.trigger_filter,
        schedule=original.schedule,
        run_at=original.run_at,
        steps=original.steps,
        language=ctx.language,
        created_by=_actor(ctx),
        updated_by=_actor(ctx),
    )
    refresh_search_text(copy)
    copy.save()
    record_event(ctx, events.FLOW_CREATED, {"id": str(copy.id)})
    return flow_row(copy)


@operation(
    "flow.flow.delete",
    kind="command",
    permission=MANAGE,
    input=FlowRefIn,
    output=DeletedOut,
    ai={
        "description": "Delete an automation, by its id or its name: it stops at once, what was waiting is "
        "cancelled and its history stays. Cannot be undone: confirm it first.",
        "risk": "high",
    },
)
def delete_flow(ctx: OperationContext, data: FlowRefIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    now = timezone.now()
    with translation.override(flow.language):
        for waiting in FlowRun.objects.select_for_update().filter(
            flow=flow, status=FlowRun.Status.WAITING
        ):
            _finish(
                ctx,
                waiting,
                FlowRun.Status.CANCELLED,
                now,
                "flow.deleted",
                str(CANCELLED_DELETED),
            )
    flow.deleted_at = now
    flow.enabled = False
    flow.next_fire_at = None
    flow.updated_by = _actor(ctx)
    flow.save(
        update_fields=[
            "deleted_at",
            "enabled",
            "next_fire_at",
            "updated_by",
            "updated_at",
        ]
    )
    record_event(ctx, events.FLOW_DELETED, {"id": str(flow.id)})
    return {"id": flow.id}


@operation(
    "flow.flow.grant",
    kind="command",
    permission=MANAGE,
    input=GrantIn,
    output=FlowOut,
    ai={
        "description": "Set the whole list of actions and reads an automation may run, by name: what is not in "
        "the list is withdrawn. A list that names something this business does not have is refused whole. "
        "An automation does nothing it was not allowed.",
        "risk": "high",
    },
)
def grant(ctx: OperationContext, data: GrantIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    problems: dict[str, str] = {}
    code = "invalid_payload"
    for index, name in enumerate(data.operations):
        problem = operation_problem(name)
        if problem is not None:
            problem_code, problems[f"operations.{index}"] = problem
            if problem_code == HIGH_RISK_CODE:
                code = HIGH_RISK_CODE
    if problems:
        raise InvalidPayload(next(iter(problems.values())), code=code, fields=problems)
    # Nobody grants more than they may do themselves (an API key with flow:write included).
    offered = catalog_operations()
    beyond = {
        f"operations.{index}": str(GRANT_BEYOND_CALLER) % {"name": name}
        for index, name in enumerate(data.operations)
        if not ctx.has(offered[name].permission)
    }
    if beyond:
        raise PermissionDenied(next(iter(beyond.values())), fields=beyond)
    flow.grants = list(dict.fromkeys(data.operations))
    flow.updated_by = _actor(ctx)
    flow.save(update_fields=["grants", "updated_by", "updated_at"])
    record_event(ctx, events.FLOW_GRANTED, {"id": str(flow.id)})
    return flow_row(flow)


# --- The assistant's drafts -------------------------------------------------------------------------


@operation(
    "flow.draft.propose",
    kind="command",
    permission=MANAGE,
    input=DraftProposeIn,
    output=DraftOut,
    ai={
        "description": "Propose a DRAFT automation — «when X happens, do Y» — whenever somebody asks for something "
        "to happen on its own («create a flow that creates a task when a sale over 100 € is completed»). "
        "It does not run, holds no permissions and waits in Automations for a person to review it and turn "
        "it on. Steps are command, condition or delay only; money is in cents (100,00 € = 10000); use "
        "the event and action names of `flow.catalog.read`. Put what you guessed in `notes`, then say it "
        "is waiting in Automations and repeat your doubts.",
        "risk": "normal",
    },
)
def propose_draft(ctx: OperationContext, data: DraftProposeIn) -> dict:
    draft = Draft.objects.create(
        name=data.name,
        definition=data.definition.model_dump(mode="json", exclude_none=True),
        notes=list(data.notes),
        created_by=_actor(ctx),
    )
    record_event(ctx, events.DRAFT_PROPOSED, {"id": str(draft.id)})
    return draft_row(draft)


@operation(
    "flow.draft.dismiss",
    kind="command",
    permission=MANAGE,
    input=DraftRefIn,
    output=DraftOut,
    ai={
        "description": "Discard a draft the assistant proposed; it stays as a record.",
        "risk": "normal",
    },
)
def dismiss_draft(ctx: OperationContext, data: DraftRefIn) -> dict:
    draft = _decide_draft(ctx, data.id, Draft.Status.DISMISSED)
    record_event(ctx, events.DRAFT_DISMISSED, {"id": str(draft.id)})
    return draft_row(draft)


# --- The engine -------------------------------------------------------------------------------------


class StepFailed(Exception):
    def __init__(
        self, code: str, message: str, fields: dict | None = None, technical: str = ""
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.fields, self.technical = (
            code,
            message,
            fields,
            technical,
        )

    def entry(self) -> dict:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fields:
            error["fields"] = self.fields
        if self.technical:
            error["technical"] = self.technical
        return error


def _log(run: FlowRun, step: dict, outcome: str, now: dt.datetime, **more: Any) -> None:
    entry = {"step": step["id"], "kind": step["kind"]}
    if step.get("operation"):
        entry["operation"] = step["operation"]
    run.log = [*run.log, {**entry, "outcome": outcome, **more, "at": now.isoformat()}]


def _start(
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
    code: str = "",
    message: str = "",
) -> None:
    run.status = status
    run.finished_at = now
    run.resume_at = None
    # What the steps read (a customer's card…) is only needed while the run may go on: none is kept,
    # except by one that stopped by an error, which may be resumed for RESUME_DAYS (FLOW-F24).
    if status != FlowRun.Status.FAILED:
        run.outputs = {}
    run.error_code = code
    run.error_message = message
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
        permissions=frozenset({op.permission}) | read_permissions(op),
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
    grantable = grantable_operations().get(name)
    if grantable is not None and needs_a_person(grantable):
        raise StepFailed(HIGH_RISK_CODE, str(HIGH_RISK) % {"name": name})
    if name not in flow.grants:
        raise StepFailed("flow.not_allowed", str(NOT_ALLOWED) % {"name": name})
    op = catalog_operations().get(name)
    if op is None or op.kind != step["kind"]:
        raise StepFailed("flow.action_unavailable", str(UNAVAILABLE) % {"name": name})
    step_ctx = _step_context(ctx, run, flow, op)
    values, _, _ = map_params(step.get("params", {}), data)
    try:
        payload = op.input.model_validate(
            prepared(op, step["kind"], step.get("result", "first"), values)
        )
    except pydantic.ValidationError as invalid:
        raise StepFailed(
            "flow.invalid_params",
            str(INVALID_PARAMS) % {"name": name},
            fields=validation_fields(invalid),
        ) from None
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
        raise StepFailed(
            "flow.step_crashed",
            str(CRASHED) % {"name": name},
            technical=f"{type(crash).__name__}: {crash}",
        ) from None
    output = result.model_dump(mode="json")
    if step["kind"] == "query":
        left, outcome, count = _read_output(step, output)
        return left, outcome, {"count": count}
    return output, "done", {}


def _advance(ctx: OperationContext, run: FlowRun, flow: Flow, now: dt.datetime) -> None:
    """Runs ``run``'s steps from ``step_index`` until it ends, waits or fails."""
    steps = run.definition.get("steps", [])
    with translation.override(flow.language):
        while run.step_index < len(steps):
            step = steps[run.step_index]
            data = {"input": run.input, "steps": run.outputs}
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
                    failure = StepFailed(
                        "flow.condition_unreadable", str(CONDITION_UNREADABLE)
                    )
                    _log(run, step, "failed", now, error=failure.entry())
                    _finish(
                        ctx, run, FlowRun.Status.FAILED, now, failure.code, failure.message
                    )
                    return
                failed = document.failed_clauses(step["when"], data)
                if failed:
                    _log(run, step, "stopped", now, failed=failed)
                    _finish(ctx, run, FlowRun.Status.STOPPED, now)
                    return
                _log(run, step, "passed", now)
                run.step_index += 1
                continue
            try:
                left, outcome, extras = _operation_step(ctx, run, flow, step, data)
            except StepFailed as failure:
                _log(run, step, "failed", now, error=failure.entry())
                _finish(
                    ctx, run, FlowRun.Status.FAILED, now, failure.code, failure.message
                )
                return
            except OperationError as refused:
                _log(
                    run,
                    step,
                    "failed",
                    now,
                    error={"code": refused.code, "message": refused.message},
                )
                _finish(
                    ctx, run, FlowRun.Status.FAILED, now, refused.code, refused.message
                )
                return
            run.outputs = {**run.outputs, step["id"]: left}
            _log(run, step, outcome, now, **extras)
            run.step_index += 1
        _finish(ctx, run, FlowRun.Status.SUCCEEDED, now)


def _parent_chain(actor: str) -> list[str]:
    """The automations behind the run that caused an event (``flow_run:<id>``); empty for anything else."""
    if not actor.startswith(RUN_ACTOR):
        return []
    try:
        parent_id = uuid.UUID(actor[len(RUN_ACTOR) :])
    except ValueError:
        return []
    parent = FlowRun.objects.filter(pk=parent_id).values("flow_id", "chain").first()
    return [*parent["chain"], str(parent["flow_id"])] if parent else []


@operation(
    "flow.run.react",
    kind="command",
    permission=SYSTEM,
    input=ReactIn,
    output=ReactOut,
    ai={
        "description": "Platform reaction to every event of the outbox: starts the automations that wait for it "
        "(once per automation and event) and runs their steps.",
        "risk": "normal",
    },
)
def react(ctx: OperationContext, data: ReactIn) -> dict:
    now = timezone.now()
    started = skipped = 0
    key = str(data.event_id)
    chain = _parent_chain(data.actor)
    waiting_ids = list(
        live_flows()
        .filter(enabled=True, trigger_kind=Flow.Trigger.EVENT, trigger_event=data.event)
        .order_by("created_at", "id")
        .values_list("pk", flat=True)
    )
    for flow_id in waiting_ids:
        flow = (
            Flow.objects.select_for_update()
            .filter(pk=flow_id, deleted_at__isnull=True, enabled=True)
            .first()
        )
        if flow is None or FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            skipped += 1
            continue
        if not document.readable(flow.trigger_filter):
            # Never «does not hold» in silence (hub#1766): the owner reads why in its history.
            run = _start(
                ctx,
                flow,
                kind=Flow.Trigger.EVENT,
                key=key,
                input=data.payload,
                now=now,
                event_name=data.event,
                chain=chain,
            )
            started += 1
            with translation.override(flow.language):
                _finish(
                    ctx,
                    run,
                    FlowRun.Status.FAILED,
                    now,
                    "flow.filter_unreadable",
                    str(FILTER_UNREADABLE),
                )
            continue
        if not document.holds(
            flow.trigger_filter, {"input": data.payload, "steps": {}}
        ):
            skipped += 1
            continue
        run = _start(
            ctx,
            flow,
            kind=Flow.Trigger.EVENT,
            key=key,
            input=data.payload,
            now=now,
            event_name=data.event,
            chain=chain,
        )
        started += 1
        with translation.override(flow.language):
            if str(flow.id) in chain:
                _finish(
                    ctx, run, FlowRun.Status.FAILED, now, "flow.loop_stopped", str(LOOP)
                )
                continue
            if len(chain) >= document.MAX_CHAIN:
                message = str(CHAIN_TOO_LONG) % {
                    "count": len(chain) + 1,
                    "max": document.MAX_CHAIN,
                }
                _finish(
                    ctx, run, FlowRun.Status.FAILED, now, "flow.loop_stopped", message
                )
                continue
        _advance(ctx, run, flow, now)
    return {"started": started, "skipped": skipped}


@operation(
    "flow.schedule.fire_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "Scheduled task, every minute: starts once each automation whose schedule or date has come, "
        "and moves its schedule on from now.",
        "risk": "normal",
    },
)
def fire_due(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    due = (
        live_flows()
        .filter(
            enabled=True,
            trigger_kind__in=[Flow.Trigger.SCHEDULE, Flow.Trigger.AT],
            next_fire_at__lte=now,
        )
        .select_for_update(skip_locked=True)
        .order_by("next_fire_at", "id")
    )
    fired = 0
    for flow in due:
        key = f"{flow.trigger_kind}:{flow.next_fire_at.astimezone(_business_zone()).isoformat()}"
        if not FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            run = _start(ctx, flow, kind=flow.trigger_kind, key=key, input={}, now=now)
            _advance(ctx, run, flow, now)
            fired += 1
        flow.next_fire_at = (
            document.next_fire(flow.schedule, now, _business_zone())
            if flow.trigger_kind == Flow.Trigger.SCHEDULE
            else None
        )
        flow.save(update_fields=["next_fire_at"])
    return {"count": fired}


@operation(
    "flow.run.resume_due",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "Scheduled task, every minute: the runs whose wait is over go on with their next step; "
        "those of a paused or deleted automation are cancelled.",
        "risk": "normal",
    },
)
def resume_due(ctx: OperationContext, data: DueIn) -> dict:
    now = timezone.now()
    due = (
        FlowRun.objects.filter(status=FlowRun.Status.WAITING, resume_at__lte=now)
        .select_related("flow")
        .select_for_update(skip_locked=True, of=("self",))
        .order_by("resume_at", "id")
    )
    resumed = 0
    for run in due:
        flow = run.flow
        with translation.override(flow.language):
            if flow.deleted_at is not None:
                _finish(
                    ctx,
                    run,
                    FlowRun.Status.CANCELLED,
                    now,
                    "flow.deleted",
                    str(CANCELLED_DELETED),
                )
                continue
            if not flow.enabled:
                _finish(
                    ctx,
                    run,
                    FlowRun.Status.CANCELLED,
                    now,
                    "flow.paused",
                    str(CANCELLED_PAUSED),
                )
                continue
        waited = [dict(entry) for entry in run.log]
        if waited and waited[-1].get("outcome") == "waiting":
            waited[-1]["outcome"] = "waited"
        run.log = waited
        run.status = FlowRun.Status.RUNNING
        run.resume_at = None
        record_event(
            ctx, events.RUN_RESUMED, {"id": str(run.id), "flow_id": str(flow.id)}
        )
        _advance(ctx, run, flow, now)
        resumed += 1
    return {"count": resumed}


@operation(
    "flow.flow.run",
    kind="command",
    permission=MANAGE,
    input=RunIn,
    output=RunOut,
    ai={
        "description": "Run an automation now, for real, by its id or its name («run the weekly review now»), "
        "with `input` as what its steps read. Only when it is on; to see what it would do without effects, "
        "use `flow.flow.test`. Confirm it first.",
        "risk": "high",
    },
)
def run_now(ctx: OperationContext, data: RunIn) -> dict:
    flow = resolve_flow(data.id, data.flow, lock=True)
    if not flow.enabled:
        with translation.override(ctx.language):
            raise Conflict(str(DISABLED), code="flow.disabled")
    now = timezone.now()
    started = _start(
        ctx,
        flow,
        kind=Flow.Trigger.MANUAL,
        key=f"manual:{uuid.uuid7()}",
        input=data.input,
        now=now,
    )
    _advance(ctx, started, flow, now)
    return run_row(started)


@operation(
    "flow.run.retry",
    kind="command",
    permission=MANAGE,
    input=RunRefIn,
    output=RunOut,
    ai={
        "description": "Resume a run that stopped by an error at the step that failed, once its cause is fixed "
        "(a permission granted, an app turned on, the other system back): the steps before it are not "
        "repeated and it goes on with the steps it started with. Only within 7 days, with the automation on. "
        "It does things for real: confirm it first.",
        "risk": "high",
    },
)
def retry_run(ctx: OperationContext, data: RunRefIn) -> dict:
    run = FlowRun.objects.filter(pk=data.id).values("flow_id").first()
    if run is None:
        raise NotFound(str(RUN_NOT_FOUND))
    # The automation first, as every write does: a save, a delete or a run wait for this one.
    flow = resolve_flow(run["flow_id"], None, lock=True)
    failed = FlowRun.objects.select_for_update().get(pk=data.id)
    now = timezone.now()
    with translation.override(ctx.language):
        problem = resume_problem(failed, now)
        if problem is not None:
            raise Conflict(problem[1], code=problem[0])
        if not flow.enabled:
            raise Conflict(str(DISABLED), code="flow.disabled")
    step = failed.definition["steps"][failed.step_index]
    _log(failed, step, "resumed", now, by=_actor(ctx))
    failed.status = FlowRun.Status.RUNNING
    failed.finished_at = None
    failed.error_code = failed.error_message = ""
    record_event(ctx, events.RUN_RESUMED, {"id": str(failed.id), "flow_id": str(flow.id)})
    _advance(ctx, failed, flow, now)
    return run_row(failed)


@operation(
    "flow.run.prune",
    kind="command",
    permission=SYSTEM,
    input=DueIn,
    output=DueOut,
    ai={
        "description": "Scheduled task, every hour: deletes the finished runs older than 90 days (the history "
        "keeps 90 days); a run that is waiting or running is never touched.",
        "risk": "normal",
    },
)
def prune_runs(ctx: OperationContext, data: DueIn) -> dict:
    cutoff = timezone.now() - dt.timedelta(days=HISTORY_DAYS)
    doomed = list(
        FlowRun.objects.filter(status__in=FINISHED)
        .annotate(ended=Coalesce("finished_at", "started_at"))
        .filter(ended__lt=cutoff)
        .order_by("ended", "id")
        .values_list("pk", flat=True)[:PRUNE_BATCH]
    )
    # A failure older than RESUME_DAYS can no longer be resumed: what its steps read goes (FLOW-F24).
    FlowRun.objects.filter(
        status=FlowRun.Status.FAILED,
        finished_at__lt=timezone.now() - dt.timedelta(days=RESUME_DAYS),
    ).exclude(outputs={}).update(outputs={})
    if doomed:
        FlowRun.objects.filter(pk__in=doomed).delete()
        # Counted: a silent prune cannot be told from lost data the day somebody looks for an old run.
        logger.info(
            "flow: deleted %d finished runs older than %d days", len(doomed), HISTORY_DAYS
        )
    return {"count": len(doomed)}
