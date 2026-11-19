"""The last time an event really happened here (``flow.event.sample``), and «Try it» (``flow.flow.test``),
which walks an automation's steps against it and executes nothing."""

from typing import Any

import pydantic
from live.context import OperationContext
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import operation, registry

from apps.flow import document, vault
from base import assistant as hub_assistant
from base.business import currency_decimals
from apps.flow.schemas import SampleIn, SampleOut, TestDocumentIn, TestIn, TestOut

from .catalog import catalog_operations, grantable_operations, needs_a_person
from .flows import resolve_flow
from .pinned import fixed_value
from .reads import MANAGE
from .values import PERSON_PARAMS, _currency, map_params, prepared, validation_fields, words_for


def _tried_pinned(ctx: OperationContext, step: Any, values: dict, unknown_steps: set[str]) -> list[dict]:
    """What «Try it» says of the data an «Ask the assistant» step fixes: each, tool by tool, with the value it would
    have as the card of the change says it (FLOW-F29: a record by its name for whoever may read it, else left out;
    never its id; an amount with the business's currency, so the screen needs no live read of its own), empty (its
    tool would not be used) or unknown (it reads a step that does not run)."""
    rows = []
    currency = _currency(ctx.scope) if step.pinned else None
    for tool, fixed in (step.pinned or {}).items():
        filled = {}
        for field, raw in fixed.items():
            reads = document.references(raw)
            if any(path.startswith("steps.") and path.split(".")[1] in unknown_steps for path in reads):
                rows.append({"tool": tool, "field": field, "said": None, "state": "unknown"})
            elif (value := fixed_value(raw, values)) is None:
                rows.append({"tool": tool, "field": field, "said": None, "state": "empty"})
            else:
                filled[field] = value
                rows.append({"tool": tool, "field": field, "said": None, "state": "filled"})
        op = registry.get(tool)
        if op is None or not filled:
            continue
        said = {field["name"]: field for field in hub_assistant.cards.card(op, filled, ctx.language, ctx)["fields"]}
        for field in said.values():
            if field["kind"] == "money" and currency and "money" not in field:
                field["money"] = {"currency": currency, "decimals": currency_decimals(currency)}
        for row in rows:
            if row["tool"] == tool and row["state"] == "filled":
                row["said"] = said.get(row["field"])
    return rows


def last_event(ctx: OperationContext, name: str) -> OutboxEvent | None:
    return (
        OutboxEvent.objects.filter(
            scope_kind=ctx.scope.kind, scope_key=ctx.scope.key, name=name
        )
        .order_by("-created_at", "-id")
        .first()
    )


def sample_of(ctx: OperationContext, name: str) -> dict[str, Any]:
    event = last_event(ctx, name)
    if event is None:
        return {"found": False, "event": name, "at": None, "payload": {}}
    return {
        "found": True,
        "event": name,
        "at": event.created_at,
        "payload": event.payload,
    }


@operation(
    "flow.event.sample",
    kind="query",
    permission=MANAGE,
    input=SampleIn,
    output=SampleOut,
    ai={
        "asks": {
            "en": (
                "what data does the sale event bring?",
                "give me a real sample of the appointment confirmed event",
            ),
            "es": (
                "¿qué datos trae el evento de una venta cobrada?",
                "¿qué trae de verdad el evento de una cita confirmada?",
            ),
        },
        "description": "The last time an event really happened in this business, with what it brought."
    },
)
def event_sample(ctx: OperationContext, data: SampleIn) -> dict:
    return sample_of(ctx, data.event)


def _clauses(failed: list[dict]) -> list[dict]:
    return [
        {"path": clause["path"], "op": clause["op"], "value": clause["value"]}
        for clause in failed
    ]


def _try_call(step: Any, values: dict, grants: list[str], unknown_steps: set[str]) -> dict:
    """What «Try it» says of a call: where it would go and with what — every secret as ``vault.MASK`` and
    the call's key as «…» (it is known when it runs) —, never calling."""
    reads = [
        path
        for path in document.references([step.url, *step.headers.values(), step.body])
        if path.startswith("steps.") and path.split(".")[1] in unknown_steps
    ]
    if reads:
        return {"outcome": "cannot_tell", "unknown": reads}
    masked = dict.fromkeys(document.secret_names(step.model_dump()), vault.MASK)
    url, headers, body = document.render_call(step.model_dump(), values, masked, "…")
    params = {"method": step.method, "url": url, "headers": headers, "body": body, "host": document.host_of(step.url)}
    granted = document.http_grant(step.url) in grants
    return {"outcome": "would_call" if granted else "not_allowed", "params": params}


@operation(
    "flow.flow.test",
    kind="query",
    permission=MANAGE,
    input=TestIn,
    output=TestOut,
    ai={
        "asks": {
            "en": (
                "try the welcome automation without doing anything for real",
                "test the birthday automation without it doing anything for real",
            ),
            "es": (
                "prueba la automatización de bienvenida sin que haga nada de verdad",
                "simula qué haría la automatización de cumpleaños con la última venta",
            ),
        },
        "description": "Try an automation without effects: walk its steps against the last time its event really "
        "happened here and say, step by step, what it would do, what would come out empty, what the action "
        "would refuse, where a condition would stop it and what it is not allowed yet. Executes nothing."
    },
)
def try_flow(ctx: OperationContext, data: TestIn) -> dict:  # noqa: C901, PLR0912, PLR0915
    grants = resolve_flow(data.id, None).grants if data.id is not None else []
    try:
        tried = TestDocumentIn.model_validate_json(data.document)
    except pydantic.ValidationError as invalid:
        fields = {f"document.{key}": message for key, message in validation_fields(invalid).items()}
        raise InvalidPayload(next(iter(fields.values())), fields=fields) from None
    trigger = tried.trigger
    sample = (
        sample_of(ctx, trigger.event)
        if trigger.kind == "event"
        else {"found": False, "event": "", "at": None, "payload": {}}
    )
    values = {"input": sample["payload"], "steps": {}}
    trigger_failed = (
        document.failed_clauses(trigger.filter, values)
        if trigger.kind == "event" and sample["found"]
        else []
    )
    stopped = bool(trigger_failed)
    operations = catalog_operations(ctx.scope)
    # What a person would read is said as the person trying it reads it (who saves it, in their language).
    say = words_for([step.model_dump() for step in tried.steps], ctx.language, ctx.scope, values, sample["event"])
    unknown_steps: set[str] = set()
    steps = []
    for step in tried.steps:
        out: dict[str, Any] = {
            "id": step.id,
            "kind": step.kind,
            "operation": getattr(step, "operation", ""),
        }
        if stopped:
            steps.append(out | {"outcome": "not_reached"})
            continue
        run_if = getattr(step, "run_if", None)
        if run_if and not any(
            path.startswith("steps.") and path.split(".")[1] in unknown_steps
            for path in [*run_if, *document.references(list(run_if.values()))]
        ):
            skipped = document.failed_clauses(run_if, values)
            if skipped:
                steps.append(out | {"outcome": "skipped", "failed": _clauses(skipped)})
                continue
        if step.kind == "delay":
            steps.append(out | {"outcome": "waits", "seconds": step.seconds})
            continue
        if step.kind == "http":
            steps.append(out | _try_call(step, values, grants, unknown_steps))
            unknown_steps.add(step.id)
            continue
        if step.kind == "ask":
            # Nothing is asked; what the person would answer is not known here.
            texts = {"title": document.fill(step.title, values, say), "details": document.fill(step.details, values, say)}
            steps.append(out | {"outcome": "would_ask", "params": texts | {"role": step.role, "hours": step.hours}})
            unknown_steps.add(step.id)
            continue
        if step.kind == "assistant":
            # Nothing is asked: what the assistant would answer is not known here.
            asked = {"prompt": document.fill(step.prompt, values), "tools": list(step.tools), "mode": step.mode}
            pinned = _tried_pinned(ctx, step, values, unknown_steps)
            steps.append(out | {"outcome": "would_ask_assistant", "params": asked, "pinned": pinned})
            unknown_steps.add(step.id)
            continue
        if step.kind == "condition":
            reads = list(step.when)
            if any(
                path.startswith("steps.") and path.split(".")[1] in unknown_steps
                for path in reads
            ):
                steps.append(out | {"outcome": "cannot_tell"})
                continue
            failed = document.failed_clauses(step.when, values)
            stopped = bool(failed)
            steps.append(
                out
                | {
                    "outcome": "stops_here" if failed else "would_run",
                    "failed": _clauses(failed),
                }
            )
            continue
        unknown_steps.add(step.id)
        op = operations.get(step.operation)
        mapped, empty, unknown = map_params(
            step.params, values, unknown_steps, say=say, person=PERSON_PARAMS.get(step.operation, ())
        )
        out |= {"params": mapped, "empty": empty, "unknown": unknown}
        grantable = grantable_operations(ctx.scope).get(step.operation)
        if grantable is not None and needs_a_person(grantable):
            steps.append(out | {"outcome": "high_risk"})
        elif op is None or op.kind != step.kind:
            steps.append(out | {"outcome": "unavailable"})
        elif step.operation not in grants:
            steps.append(out | {"outcome": "not_allowed"})
        elif unknown:
            steps.append(out | {"outcome": "cannot_tell"})
        else:
            try:
                op.input.model_validate(
                    prepared(op, step.kind, getattr(step, "result", "first"), mapped)
                )
            except pydantic.ValidationError as invalid:
                steps.append(
                    out | {"outcome": "refused", "errors": validation_fields(invalid)}
                )
            else:
                steps.append(out | {"outcome": "would_run"})
    return {
        "sample": sample,
        "starts": not trigger_failed,
        "trigger_failed": _clauses(trigger_failed),
        "steps": steps,
    }
