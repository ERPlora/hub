"""What the model hears of a read that the caller's role keeps to their own (``base.queries.ownership.only_theirs``).

The model never sees the rule: an answer without a colleague's rows reads to it as «she has none» (hub#2688)."""

import json

from live.assistant import ToolOutcome

#: Where a tool's result says it holds only the person's own.
ONLY_THEIRS = "only_theirs"
#: What it says.
SAID = (
    "Only the person's own: their role hides everyone else's. Asked about another person, say you can only see "
    "theirs, never that the other has none."
)


def told(outcome: ToolOutcome) -> ToolOutcome:
    """``outcome`` with ``ONLY_THEIRS`` first in its answer, its rows or its refusal alike; a refusal of the person
    (no permission, the app off) is about the tool, not about whose rows it reads, and stays as it is."""
    if outcome.outcome not in ("ok", "error"):
        return outcome
    answer = {ONLY_THEIRS: SAID, **json.loads(outcome.content)}
    return ToolOutcome(outcome.outcome, outcome.code, json.dumps(answer, ensure_ascii=False, separators=(",", ":")))
