"""A read that the caller's role keeps to their own («view own / view all»), told to the assistant's model.

The model never sees that rule: an answer without a colleague's rows reads to it as «she has none». So whatever decides
that a read keeps the caller to their own calls ``only_theirs`` (an ``Owned`` declaration does it by itself), and the
tool's result says the answer holds only the person's own (``told``)."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from live.assistant import ToolOutcome

#: Where a tool's result says it holds only the person's own.
ONLY_THEIRS = "only_theirs"
#: What it says.
SAID = (
    "Only the person's own: their role hides everyone else's. Asked about another person, say you can only see "
    "theirs, never that the other has none."
)

_HEARD: ContextVar[list[bool] | None] = ContextVar("only_theirs", default=None)


def only_theirs() -> None:
    """Says that the read running answers only the caller's own."""
    heard = _HEARD.get()
    if heard is not None:
        heard.append(True)


@contextmanager
def hearing() -> Iterator[list[bool]]:
    """A list that is not empty when what runs inside said it answers only the caller's own."""
    heard: list[bool] = []
    token = _HEARD.set(heard)
    try:
        yield heard
    finally:
        _HEARD.reset(token)


def told(outcome: ToolOutcome) -> ToolOutcome:
    """``outcome`` with ``ONLY_THEIRS`` first in its answer, its rows or its refusal alike; a refusal of the person
    (no permission, the app off) is about the tool, not about whose rows it reads, and stays as it is."""
    if outcome.outcome not in ("ok", "error"):
        return outcome
    answer = {ONLY_THEIRS: SAID, **json.loads(outcome.content)}
    return ToolOutcome(outcome.outcome, outcome.code, json.dumps(answer, ensure_ascii=False, separators=(",", ":")))
