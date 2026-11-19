"""The runs of an automation (``flow.run.list`` and ``flow.run.get``) and whether one can be resumed from the
step that failed (FLOW-F24)."""

import datetime as dt
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.flow.models import FlowRun
from apps.flow.schemas import RunDetailOut, RunListIn, RunPageOut, RunRefIn

from .problems import HIGH_RISK_CODE
from .reads import VIEW
from .reasons import _said_entry, say
from .values import _moment_words

RUN_NOT_FOUND = _("That run does not exist in this business.")

#: How long a run that stopped by an error keeps what its steps left, to be resumed (FLOW-F24); after
#: that, the hourly prune forgets it (what a step read is never kept longer than a wait could).
RESUME_DAYS = 7
#: Failures that happened before any step ran, or that the same steps would hit again for sure.
NOT_RESUMABLE = frozenset(
    {
        "flow.loop_stopped",
        "flow.filter_unreadable",
        "flow.condition_unreadable",
        "flow.run_if_unreadable",
        HIGH_RISK_CODE,
        # A call to an address that is not plain https, or inside a private network: the same steps would
        # be refused again (FLOW-F27); the step has to change, and a resumed run keeps the steps it started with.
        "flow.http_url_invalid",
        "flow.http_blocked",
    }
)
#: The kinds of step whose output later steps read (``steps.<id>``).
LEAVES = ("command", "query", "http", "ask", "assistant")
RUN_NOT_RESUMABLE = _("Only a run that stopped by an error at one of its steps can be resumed.")
BEFORE_ANY_STEP = _(
    "This run cannot be resumed: it stopped before doing any step, or would stop there again. Run it "
    "again whole."
)
RESUME_EXPIRED = _(
    "This run can no longer be resumed: it stopped more than %(days)s days ago and no longer keeps what "
    "its steps did. Run it again whole."
)


def resume_problem(run: FlowRun, now) -> tuple[str, str] | None:
    """``(code, message)`` of why ``run`` cannot be resumed at the step that failed, or ``None``.

    It must have stopped by an error at a step (its last entry), still keep what every earlier step left
    and have stopped less than ``RESUME_DAYS`` ago.
    """
    steps = run.definition.get("steps", [])
    if run.status != FlowRun.Status.FAILED:
        return "flow.run_not_resumable", str(RUN_NOT_RESUMABLE)
    last = run.log[-1] if run.log else {}
    at_a_step = (
        run.step_index < len(steps)
        and last.get("outcome") == "failed"
        and last.get("step") == steps[run.step_index].get("id")
    )
    if not at_a_step or run.error_code in NOT_RESUMABLE:
        return "flow.run_not_resumable", str(BEFORE_ANY_STEP)
    ended = run.finished_at or run.started_at
    lost = any(
        step.get("kind") in LEAVES and step.get("id") not in run.outputs
        for step in steps[: run.step_index]
    )
    if lost or ended < now - dt.timedelta(days=RESUME_DAYS):
        return "flow.resume_expired", str(RESUME_EXPIRED) % {"days": RESUME_DAYS}
    return None


def run_row(run: FlowRun) -> dict[str, Any]:
    return {
        "resumable": resume_problem(run, timezone.now()) is None,
        "id": run.id,
        "flow_id": run.flow_id,
        "flow_version": run.flow_version,
        "status": run.status,
        "trigger_kind": run.trigger_kind,
        "event_name": run.event_name,
        "input": run.input,
        "step_index": run.step_index,
        "steps_total": len(run.definition.get("steps", [])),
        "log": [_said_entry(entry) for entry in run.log],
        "error_code": run.error_code,
        "error_message": say(run.error_reason or {"key": run.error_code}, run.error_message),
        "resume_at": run.resume_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "started_by": run.started_by,
    }


@operation(
    "flow.run.list",
    kind="query",
    permission=VIEW,
    input=RunListIn,
    output=RunPageOut,
    ai={
        "asks": {
            "en": (
                "what did the welcome automation do this week?",
                "why did the birthday automation fail?",
            ),
            "es": (
                "¿qué ha hecho la automatización de bienvenida esta semana?",
                "¿por qué falló la automatización de cumpleaños?",
                "¿qué ejecuciones de la automatización de recordatorios han fallado?",
            ),
        },
        "description": "What an automation did, the newest first: each run's status (finished well, stopped by a "
        "condition, stopped by an error, waiting, cancelled), each step and the reason of a failure; and how "
        "many runs failed («why did the welcome automation fail?»)."
    },
)
def list_runs(ctx: OperationContext, data: RunListIn) -> dict:
    runs = FlowRun.objects.filter(flow_id=data.flow_id)
    failed = runs.aggregate(failed=Count("id", filter=Q(status=FlowRun.Status.FAILED)))[
        "failed"
    ]
    if data.status is not None:
        runs = runs.filter(status=data.status)
    total = runs.count()
    page = runs.order_by("-started_at", "-id")[data.offset : data.offset + data.limit]
    with translation.override(ctx.language):
        rows = [run_row(run) for run in page]
    return {
        "rows": rows,
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
        "failed": failed,
    }


def run_label(run: FlowRun, language: str) -> str:
    """As the History names a run, with its automation in front (out of its History it says whose): «Welcome · Oct 15,
    2026, 9:00 PM», when it started at the business's hour."""
    return f"{run.flow.name} · {_moment_words(run.started_at.isoformat(), language)}"


@operation(
    "flow.run.get",
    kind="query",
    permission=VIEW,
    input=RunRefIn,
    output=RunDetailOut,
    ai={
        "asks": {
            "en": (
                "open that run and tell me which step failed",
                "show me the details of this morning's run",
            ),
            "es": (
                "¿en qué paso se paró esa ejecución y por qué?",
                "dame el detalle de la ejecución de esta mañana",
            ),
        },
        "description": "One run by its id (its reference in the History): how it ended or where it waits, each step, "
        "the reason of a failure and whether it can be resumed; named by its automation and when it started."
    },
)
def get_run(ctx: OperationContext, data: RunRefIn) -> dict:
    found = FlowRun.objects.select_related("flow").filter(pk=data.id).first()
    with translation.override(ctx.language):
        if found is None:
            raise NotFound(str(RUN_NOT_FOUND))
        return {**run_row(found), "label": run_label(found, ctx.language)}
