"""An edit the assistant asks for with nothing to change: no card for it, and the model hears why (BASE-F97).

An edit (``<app>.<entity>.update``) changes only the data it sends. What names its record is what the record's read
(``<app>.<entity>.get`` or ``.detail``) takes to find it; anything else it sends is a change. A call that sends nothing
else would show a card that changes nothing, and its yes would report as done what did not change.
"""

from live.assistant import ToolOutcome, refusal
from live.operations import Operation, registry

#: The code of the edit that names nothing to change: the model hears it, and the receipt says why.
NOTHING_TO_CHANGE = "base.assistant_nothing_to_change"
#: What the model hears of it (in English, as its instructions).
TOLD = (
    "Nothing to change: the call names the record but no data to change, so nothing was done and no card was shown. "
    "Do what the person asked with the tool that does it (search for it if you do not have it), or ask them what to "
    "change."
)


def unchanged(op: Operation, arguments: dict) -> ToolOutcome | None:
    """The refusal of the edit ``op`` when ``arguments`` name its record and nothing to change; ``None`` for any other
    write, or for an edit that sends something to change."""
    entity, action = op.name.rsplit(".", 1)
    if action != "update":
        return None
    record = next((registry[name] for name in (f"{entity}.get", f"{entity}.detail") if name in registry), None)
    names_it = set(record.input.model_fields) if record is not None else set()
    if any(name not in names_it for name in arguments):
        return None
    return refusal("error", NOTHING_TO_CHANGE, TOLD)
