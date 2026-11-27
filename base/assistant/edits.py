"""An edit the assistant asks for: one with nothing to change, and what the model hears once its card is answered
(BASE-F97).

An edit (``<app>.<entity>.update``, or ``<what>_update`` and ``<what>_set`` of its ``<what>``) changes only the data it
sends. What names its record is what the record's read (``state_read``) takes to find it; anything else it sends is a
change. A call that sends nothing else would show a card that changes nothing, and its yes would report as done what did
not change. Once its card is answered, the model hears how the data it sent stood and stand: what changed from what to
what and what was already so after a yes, how they stay after a no. It never has to guess what was there before.
"""

import dataclasses
import json
from typing import Any

from live.assistant import MAX_RESULT_CHARS, ToolOutcome, refusal
from live.context import OperationContext
from live.operations import Operation, registry

from .tools import run

#: The code of the edit that names nothing to change: the model hears it, and the receipt says why.
NOTHING_TO_CHANGE = "base.assistant_nothing_to_change"
#: What the model hears of it (in English, as its instructions).
TOLD = (
    "Nothing to change: the call names the record but no data to change, so nothing was done and no card was shown. "
    "Do what the person asked with the tool that does it (search for it if you do not have it), or ask them what to "
    "change."
)


def state_read(op: Operation) -> Operation | None:
    """The read of the record the edit ``op`` changes, or ``None`` for any other write: ``<entity>.<what>`` for an edit
    of its ``<what>``, else ``<entity>.get`` or ``.detail``."""
    entity, action = op.name.rsplit(".", 1)
    what, _, verb = action.rpartition("_")
    if action != "update" and verb not in ("update", "set"):
        return None
    names = (f"{entity}.{what}", f"{entity}.get", f"{entity}.detail") if what else (f"{entity}.get", f"{entity}.detail")
    return next((registry[name] for name in names if name in registry and registry[name].kind == "query"), None)


def unchanged(op: Operation, arguments: dict) -> ToolOutcome | None:
    """The refusal of the edit ``op`` when ``arguments`` name its record and nothing to change; ``None`` for any other
    write, or for an edit that sends something to change."""
    if op.name.rsplit(".", 1)[1] != "update":
        return None
    record = state_read(op)
    names_it = set(record.input.model_fields) if record is not None else set()
    if any(name not in names_it for name in arguments):
        return None
    return refusal("error", NOTHING_TO_CHANGE, TOLD)


def as_it_stands(ctx: OperationContext, op: Operation, arguments: dict) -> dict | None:
    """The record the edit ``op`` with ``arguments`` changes, as its read answers ``ctx``'s person now and as the model
    reads every answer (``run``: its hours and amounts as the screens write them); ``None`` for another write, or when
    it cannot be read."""
    read = state_read(op)
    if read is None:
        return None
    named = {name: value for name, value in arguments.items() if name in read.input.model_fields}
    read_now = run(ctx, read, json.dumps(named))
    return _answer(read_now.content) if read_now.outcome == "ok" else None


def heard(op: Operation, arguments: dict, before: dict | None, outcome: ToolOutcome) -> ToolOutcome:
    """What the model hears of the edit ``op`` called with ``arguments`` once its card is answered, with the data it
    sent as they stood (``before``, ``as_it_stands``): after a yes, its answer with what changed from what to what
    (``changed``) and what was already so (``already_so``); after a no, how they stay (``as_it_stands``). Another
    write, one that failed or one whose data are not in its record's answer is heard as it ended."""
    if outcome.outcome == "cancelled":
        return _with(outcome, _stand(op, arguments, before, _answer(outcome.content)))
    if outcome.outcome == "ok":
        return _with(outcome, _changes(op, arguments, before, _answer(outcome.content)))
    return outcome


def _stand(op: Operation, arguments: dict, before: dict | None, said: dict | None) -> dict | None:
    keys = _keys(op, arguments, before)
    if not keys or said is None:
        return None
    return {"as_it_stands": {key: before[key] for key in keys}, **said}


def _changes(op: Operation, arguments: dict, before: dict | None, after: dict | None) -> dict | None:
    keys = [key for key in _keys(op, arguments, before) if after is not None and key in after]
    if not keys:
        return None
    changed = {key: {"from": before[key], "to": after[key]} for key in keys if before[key] != after[key]}
    return {"changed": changed, "already_so": [key for key in keys if key not in changed], **after}


def _with(outcome: ToolOutcome, told: dict | None) -> ToolOutcome:
    """``outcome`` with ``told`` as what the model hears of it, when there is something to tell and it fits."""
    content = json.dumps(told, ensure_ascii=False, separators=(",", ":")) if told is not None else ""
    return dataclasses.replace(outcome, content=content) if 0 < len(content) <= MAX_RESULT_CHARS else outcome


def _keys(op: Operation, arguments: dict, before: dict | None) -> list[str]:
    """The data of ``arguments`` the edit ``op`` changes (not the ones that name its record), by the name its record's
    answer ``before`` gives each: its own, or ``<datum>_id`` for one that names another record by its id or its name."""
    read = state_read(op)
    if read is None or before is None:
        return []
    named = [name if name in before else f"{name}_id" for name in arguments if name not in read.input.model_fields]
    return [key for key in named if key in before]


def _answer(content: str) -> dict | None:
    try:
        answer: Any = json.loads(content)
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None
