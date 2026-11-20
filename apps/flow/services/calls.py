"""The calls to another system (FLOW-F27): made by the worker after the COMMIT, with their secrets filled in
and the same idempotency key in every attempt, and how each one ended recorded."""

import datetime as dt
import uuid

from django.utils import timezone, translation
from live.context import OperationContext, Scope, system_context
from live.operations import get, operation

from apps.flow import document, http, vault
from apps.flow.models import FlowRun, Secret
from apps.flow.queries.reads import SYSTEM
from apps.flow.schemas.calls import ClaimCallOut, RecordCallIn
from apps.flow.schemas.fields import DueOut
from apps.flow.schemas.runs import RunRefIn
from base import outbound

from .assistant_steps import dispatch_assistant, _due_calling_run
from .engine import StepFailed, _call_allowed, _call_failed, _finish, _go_on, _log, _own
from .writes import CALL_LEASE_MINUTES

#: A call's ``Idempotency-Key`` is ``uuid5(IDEMPOTENCY_NAMESPACE, "<run id>:<step id>")``: the same in every
#: attempt of a run's step, another in every run.
IDEMPOTENCY_NAMESPACE = uuid.UUID("0199f6a0-6b1f-7c3e-9a51-3f1b2c4d5e6f")
#: How a call that did not answer 2xx ends: its code (and the name of its reason, ``queries.reasons.REASONS``).
_CALL_FAILURES = {
    http.STATUS: "flow.http_status",
    http.BLOCKED: "flow.http_blocked",
    http.FAILED: "flow.http_failed",
    http.TIMEOUT: "flow.http_timeout",
    http.INVALID: "flow.http_url_invalid",
}


def dispatch_call(scope: Scope, run_id: uuid.UUID) -> None:
    """Makes a run's call, with no transaction and no lock around it, and records how it ended in a
    transaction of its own: ``flow.run.claim_call`` → ``http.call`` → ``flow.run.record_call``. A call
    another process holds, or that ended meanwhile, is left alone."""
    system = system_context(scope)
    claimed = get("flow.run.claim_call")(system, RunRefIn(id=run_id))
    if not claimed.claimed:
        return
    outbound.release()  # the call waits on the other system with no connection held
    reply = http.call(claimed.method, claimed.url, claimed.headers, claimed.body, claimed.timeout)
    get("flow.run.record_call")(
        system,
        RecordCallIn(
            id=run_id,
            kind=reply.kind,
            status=reply.status,
            body=vault.mask_any(reply.body, claimed.masks),
            truncated=reply.truncated,
            detail=vault.mask(reply.detail, claimed.masks)[:2000],
        ),
    )


@operation(
    "flow.run.call",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=DueOut,
    ai={
        "description": "System only, in the worker: the reaction to `flow.run.parked` — a run that is calling "
        "makes its call after this COMMIT (`flow.run.claim_call` → the call → `flow.run.record_call`), never "
        "inside a person's request; a run that waits or asks has nothing to call.",
        "risk": "normal",
    },
)
def call_parked(ctx: OperationContext, data: RunRefIn) -> dict:
    parked = FlowRun.objects.filter(pk=data.id, status=FlowRun.Status.CALLING).values("definition", "step_index").first()
    if parked is None:
        return {"count": 0}
    outbound.after_commit(_dispatcher(parked), ctx.scope, data.id)
    return {"count": 1}


def _dispatcher(parked: dict):
    """What a run that waits on something outside the Hub makes, outside any transaction: its call, or its turn."""
    step = parked["definition"]["steps"][parked["step_index"]]
    return dispatch_assistant if step["kind"] == "assistant" else dispatch_call


@operation(
    "flow.run.claim_call",
    kind="command",
    permission=SYSTEM,
    input=RunRefIn,
    output=ClaimCallOut,
    ai={
        "description": "System only: takes a run's call to another system to make it (nobody else holds it), "
        "with its data and secrets filled in, for CALL_LEASE_MINUTES.",
        "risk": "normal",
    },
)
def claim_call(ctx: OperationContext, data: RunRefIn) -> dict:
    now = timezone.now()
    run = _due_calling_run(data, now)
    if run is None:
        return {"claimed": False}
    flow = run.flow
    step = run.definition["steps"][run.step_index]
    with translation.override(flow.language):
        if flow.deleted_at is not None:
            _finish(ctx, run, FlowRun.Status.CANCELLED, now, _own("flow.deleted"))
            return {"claimed": False}
        refused = _call_allowed(run, flow, step)
        if refused is None:
            secrets, refused = _open_secrets(document.secret_names(step))
        if refused is not None:
            _call_failed(ctx, run, flow, step, refused, now)
            return {"claimed": False}
    key = str(uuid.uuid5(IDEMPOTENCY_NAMESPACE, f"{run.id}:{step['id']}"))
    url, headers, body = document.render_call(step, {"input": run.input, "steps": run.outputs}, secrets, key)
    if not any(name.lower() == "idempotency-key" for name in headers):
        headers["Idempotency-Key"] = key
    run.resume_at = now + dt.timedelta(minutes=CALL_LEASE_MINUTES)
    run.save(update_fields=["resume_at"])
    return {
        "claimed": True,
        "method": step.get("method", "POST"),
        "url": url,
        "headers": headers,
        "body": body,
        "timeout": int(step.get("timeout", 10)),
        "masks": list(secrets.values()),
    }


def _open_secrets(names: list[str]) -> tuple[dict[str, str], StepFailed | None]:
    """The values of the secrets a call reads, or why it cannot make it."""
    if not names:
        return {}, None
    if not vault.available():
        return {}, _own("flow.secrets_key_missing")
    kept = dict(Secret.objects.filter(name__in=names).values_list("name", "ciphertext"))
    opened: dict[str, str] = {}
    for name in names:
        if name not in kept:
            return {}, _own("flow.secret_not_found", name=name)
        try:
            opened[name] = vault.open_value(kept[name])
        except vault.Unreadable:
            return {}, _own("flow.secret_unreadable", name=name)
    return opened, None


@operation(
    "flow.run.record_call",
    kind="command",
    permission=SYSTEM,
    input=RecordCallIn,
    output=DueOut,
    ai={
        "description": "System only: records how a run's call to another system ended and goes on with the run "
        "(or stops it with the reason); an answer for a run that is no longer calling changes nothing.",
        "risk": "normal",
    },
)
def record_call(ctx: OperationContext, data: RecordCallIn) -> dict:
    now = timezone.now()
    run = FlowRun.objects.select_for_update(of=("self",)).select_related("flow").filter(pk=data.id).first()
    if run is None or run.status != FlowRun.Status.CALLING:
        return {"count": 0}
    flow = run.flow
    step = run.definition["steps"][run.step_index]
    host = document.host_of(step["url"])
    with translation.override(flow.language):
        if data.kind == http.OK:
            run.outputs = {
                **run.outputs,
                step["id"]: {"ok": True, "status": data.status, "body": data.body, "truncated": data.truncated},
            }
            _log(run, step, "called", now, host=host, status=data.status)
            run.step_index += 1
            _go_on(ctx, run, flow, now)
            return {"count": 1}
        failure = _own(
            _CALL_FAILURES[data.kind],
            technical=data.detail,
            host=host,
            status=data.status,
            seconds=step.get("timeout", 10),
        )
        _call_failed(ctx, run, flow, step, failure, now, {"status": data.status})
    return {"count": 1}
