"""The last time an event really happened here (``flow.event.sample``), and «Try it» (``flow.flow.test``),
which walks an automation's steps against it and executes nothing."""

import dataclasses
from typing import Any

import pydantic
from live.context import OperationContext
from live.errors import InvalidPayload
from live.models import OutboxEvent
from live.operations import Operation, operation, registry

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


@dataclasses.dataclass
class _Walk:
    """What «Try it» knows as it walks an automation's steps: the data a step reads, the steps whose answer is not known
    here (they would call, ask or act), whether a condition already stopped the run, and how a text a person reads
    says each datum."""

    ctx: OperationContext
    grants: list[str]
    values: dict
    say: document.Say
    operations: dict[str, Operation]
    stopped: bool = False
    unknown: set[str] = dataclasses.field(default_factory=set)

    def reads_unknown(self, paths: list[str]) -> bool:
        """Whether one of ``paths`` reads the answer of a step not known here."""
        return any(path.startswith("steps.") and path.split(".")[1] in self.unknown for path in paths)


def _try_call(walk: _Walk, step: Any) -> dict:
    """What «Try it» says of a call: where it would go and with what — every secret as ``vault.MASK`` and
    the call's key as «…» (it is known when it runs) —, never calling."""
    reads = [
        path
        for path in document.references([step.url, *step.headers.values(), step.body])
        if path.startswith("steps.") and path.split(".")[1] in walk.unknown
    ]
    if reads:
        return {"outcome": "cannot_tell", "unknown": reads}
    masked = dict.fromkeys(document.secret_names(step.model_dump()), vault.MASK)
    url, headers, body = document.render_call(step.model_dump(), walk.values, masked, "…")
    params = {"method": step.method, "url": url, "headers": headers, "body": body, "host": document.host_of(step.url)}
    granted = document.http_grant(step.url) in walk.grants
    return {"outcome": "would_call" if granted else "not_allowed", "params": params}


def _tried_ask(walk: _Walk, step: Any) -> dict:
    """The question «Ask someone first» would ask, its texts as the person will read them; nothing is asked."""
    texts = {"title": document.fill(step.title, walk.values, walk.say), "details": document.fill(step.details, walk.values, walk.say)}
    return {"outcome": "would_ask", "params": texts | {"role": step.role, "hours": step.hours}}


def _tried_assistant(walk: _Walk, step: Any) -> dict:
    """What «Ask the assistant» would ask it, and the data it fixes; nothing is asked."""
    asked = {"prompt": document.fill(step.prompt, walk.values), "tools": list(step.tools), "mode": step.mode}
    pinned = _tried_pinned(walk.ctx, step, walk.values, walk.unknown)
    return {"outcome": "would_ask_assistant", "params": asked, "pinned": pinned}


#: The steps whose answer is not known here — a call, a question, the assistant —: a step after them that reads it
#: cannot be told.
_ANSWERED_LATER = {"http": _try_call, "ask": _tried_ask, "assistant": _tried_assistant}


def _tried_condition(walk: _Walk, step: Any) -> dict:
    """Whether a «Continue only if…» would let the run go on; one that reads a step not known here cannot be told."""
    if walk.reads_unknown(list(step.when)):
        return {"outcome": "cannot_tell"}
    failed = document.failed_clauses(step.when, walk.values)
    walk.stopped = bool(failed)
    return {"outcome": "stops_here" if failed else "would_run", "failed": _clauses(failed)}


def _skipped(walk: _Walk, step: Any) -> list[dict]:
    """The clauses of a step's «Only run if…» that do not hold; none when it has none or reads a step not known here."""
    run_if = getattr(step, "run_if", None)
    if not run_if or walk.reads_unknown([*run_if, *document.references(list(run_if.values()))]):
        return []
    return document.failed_clauses(run_if, walk.values)


def _action_outcome(walk: _Walk, step: Any, mapped: dict, unknown: list[str]) -> dict:
    """What an action or a read would do with ``mapped``: refused before it runs (it needs a person, it is not
    available or not allowed, its data say no), not told (it reads a step not known here) or run."""
    op = walk.operations.get(step.operation)
    grantable = grantable_operations(walk.ctx.scope).get(step.operation)
    if grantable is not None and needs_a_person(grantable):
        return {"outcome": "high_risk"}
    if op is None or op.kind != step.kind:
        return {"outcome": "unavailable"}
    if step.operation not in walk.grants:
        return {"outcome": "not_allowed"}
    if unknown:
        return {"outcome": "cannot_tell"}
    try:
        op.input.model_validate(prepared(op, step.kind, getattr(step, "result", "first"), mapped))
    except pydantic.ValidationError as invalid:
        return {"outcome": "refused", "errors": validation_fields(invalid)}
    return {"outcome": "would_run"}


def _tried_action(walk: _Walk, step: Any) -> dict:
    """An action's or a read's data as it would get them, and what it would do with them."""
    walk.unknown.add(step.id)
    mapped, empty, unknown = map_params(
        step.params, walk.values, walk.unknown, say=walk.say, person=PERSON_PARAMS.get(step.operation, ())
    )
    return {"params": mapped, "empty": empty, "unknown": unknown} | _action_outcome(walk, step, mapped, unknown)


def _tried_step(walk: _Walk, step: Any) -> dict:
    """What one step would do, in order: not reached once a condition stopped the run, skipped when its «Only run if…»
    does not hold, else what its kind does."""
    out: dict[str, Any] = {"id": step.id, "kind": step.kind, "operation": getattr(step, "operation", "")}
    if walk.stopped:
        return out | {"outcome": "not_reached"}
    if skipped := _skipped(walk, step):
        return out | {"outcome": "skipped", "failed": _clauses(skipped)}
    if step.kind == "delay":
        return out | {"outcome": "waits", "seconds": step.seconds}
    if step.kind == "condition":
        return out | _tried_condition(walk, step)
    if answered_later := _ANSWERED_LATER.get(step.kind):
        said = answered_later(walk, step)
        walk.unknown.add(step.id)
        return out | said
    return out | _tried_action(walk, step)


def _tried_document(document_json: str) -> TestDocumentIn:
    """The automation to try, or ``InvalidPayload`` naming the first datum of it that does not hold."""
    try:
        return TestDocumentIn.model_validate_json(document_json)
    except pydantic.ValidationError as invalid:
        fields = {f"document.{key}": message for key, message in validation_fields(invalid).items()}
        raise InvalidPayload(next(iter(fields.values())), fields=fields) from None


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
def try_flow(ctx: OperationContext, data: TestIn) -> dict:
    grants = resolve_flow(data.id, None).grants if data.id is not None else []
    tried = _tried_document(data.document)
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
    # What a person would read is said as the person trying it reads it (who saves it, in their language).
    say = words_for([step.model_dump() for step in tried.steps], ctx.language, ctx.scope, values, sample["event"])
    walk = _Walk(ctx, grants, values, say, catalog_operations(ctx.scope), stopped=bool(trigger_failed))
    return {
        "sample": sample,
        "starts": not trigger_failed,
        "trigger_failed": _clauses(trigger_failed),
        "steps": [_tried_step(walk, step) for step in tried.steps],
    }
