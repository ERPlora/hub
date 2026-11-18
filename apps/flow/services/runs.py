"""How a run starts and goes on: by an event of another active app (``flow.run.react``), a schedule or a date
(``flow.schedule.fire_due``), by hand (``flow.flow.run``), after a wait (``flow.run.resume_due``) and
resumed from the step that failed (``flow.run.retry``)."""

import uuid

from django.utils import timezone, translation
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.flow import document, events, recipes
from apps.flow.apps import RUN_ACTOR
from apps.flow.models import Flow, FlowRun
from apps.flow.queries import (
    RUN_NOT_FOUND,
    MANAGE,
    SYSTEM,
    active_apps,
    resume_problem,
    live_flows,
    resolve_flow,
    run_row,
)
from apps.flow.schemas import DueIn, DueOut, ReactIn, ReactOut, RunIn, RunOut, RunRefIn
from base import outbound
from base.business import business_zone
from base.recovery import brought_back

from .calls import _dispatcher
from .engine import _advance, _finish, _log, _own, _start
from .writes import DISABLED, _actor


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
        "description": "System only: the platform's reaction to every event of the outbox: starts the automations "
        "that wait for it (once per automation and event) and runs their steps.",
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
    if waiting_ids and data.event.split(".", 1)[0] not in active_apps(ctx.scope):
        return {"started": 0, "skipped": len(waiting_ids)}
    if waiting_ids and brought_back(data.actor):
        # What a recovery brought back from a separate copy is nothing new to the business (BASE-F114, hub#1307): no
        # automation greets or announces it again.
        return {"started": 0, "skipped": len(waiting_ids)}
    for flow_id in waiting_ids:
        flow = (
            Flow.objects.select_for_update()
            .filter(pk=flow_id, deleted_at__isnull=True, enabled=True)
            .first()
        )
        if flow is None or FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            skipped += 1
            continue
        # What its recipe excludes today counts too, whenever it was built (FLOW-F36).
        wanted = recipes.fixed_filter(flow)
        if not document.readable(wanted):
            # Never «does not hold» in silence: the owner reads why in its history.
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
                _finish(ctx, run, FlowRun.Status.FAILED, now, _own("flow.filter_unreadable"))
            continue
        if not document.holds(wanted, {"input": data.payload, "steps": {}}):
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
                _finish(ctx, run, FlowRun.Status.FAILED, now, _own("flow.loop_stopped", "flow.loop"))
                continue
            if len(chain) >= document.MAX_CHAIN:
                too_long = _own(
                    "flow.loop_stopped", "flow.chain_too_long", count=len(chain) + 1, max=document.MAX_CHAIN
                )
                _finish(ctx, run, FlowRun.Status.FAILED, now, too_long)
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
        "description": "System only, a scheduled task, every minute: starts once each automation whose schedule or "
        "date has come, and moves its schedule on from now.",
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
        key = f"{flow.trigger_kind}:{flow.next_fire_at.astimezone(business_zone()).isoformat()}"
        if not FlowRun.objects.filter(flow=flow, trigger_key=key).exists():
            run = _start(ctx, flow, kind=flow.trigger_kind, key=key, input={}, now=now)
            _advance(ctx, run, flow, now)
            fired += 1
        flow.next_fire_at = (
            document.next_fire(flow.schedule, now, business_zone())
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
        "description": "System only, a scheduled task, every minute: the runs whose wait is over go on with their "
        "next step; those of a paused or deleted automation are cancelled.",
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
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
                continue
            if not flow.enabled:
                _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.paused"))
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
    # A call (or a turn of the assistant) whose lease ran out never answered (the process died): it goes again.
    stuck = (
        FlowRun.objects.filter(status=FlowRun.Status.CALLING, resume_at__lte=now)
        .select_for_update(skip_locked=True)
        .order_by("resume_at", "id")
        .values("pk", "definition", "step_index")
    )
    for parked in stuck:
        outbound.after_commit(_dispatcher(parked), ctx.scope, parked["pk"])
        resumed += 1
    return {"count": resumed}


@operation(
    "flow.flow.run",
    kind="command",
    permission=MANAGE,
    input=RunIn,
    output=RunOut,
    ai={
        "asks": {
            "en": (
                "run the weekly review automation now",
                "launch the reminders automation right away",
            ),
            "es": (
                "ejecuta ya la automatización de la revisión semanal",
                "lanza ahora mismo la automatización de los recordatorios",
            ),
        },
        "description": "Run an automation now, for real, by its id or its name («run the weekly review now»), "
        "with `input` as what its steps read. Only when it is on; to see what it would do without effects, "
        "use `flow.flow.test`.",
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
    with translation.override(ctx.language):
        return run_row(started)


@operation(
    "flow.run.retry",
    kind="command",
    permission=MANAGE,
    input=RunRefIn,
    output=RunOut,
    ai={
        "asks": {
            "en": (
                "retry the failed run now that the permission is granted",
                "resume the run that stopped with an error",
            ),
            "es": (
                "vuelve a intentar la ejecución de anoche, ya he dado el permiso que faltaba",
                "vuelve a lanzar desde el error la ejecución de ayer",
            ),
        },
        "description": "Resume a run that stopped by an error at the step that failed, once its cause is fixed "
        "(a permission granted, an app turned on, the other system back): the steps before it are not "
        "repeated and it goes on with the steps it started with. Only within 7 days, with the automation on. "
        "It does things for real.",
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
    failed.error_reason = {}
    record_event(ctx, events.RUN_RESUMED, {"id": str(failed.id), "flow_id": str(flow.id)})
    _advance(ctx, failed, flow, now)
    with translation.override(ctx.language):
        return run_row(failed)
