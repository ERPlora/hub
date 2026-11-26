"""The card of a write that creates several records at once (``ai={"summary": …}``) — an import from a file, people or
services the person dictates —: its rows by the name each one gives."""

from collections.abc import Callable
from typing import Any

from live.assistant import NAMED
from live.context import OperationContext

Summary = Callable[[OperationContext, dict, list[dict]], list[dict]]


def _name(row: Any, keys: tuple[str, ...]) -> str | None:
    """The name a row gives by its data ``keys``, each trimmed as the write keeps it and joined as a name is written
    («Carla» and «Ruiz QA», «Carla Ruiz QA»); none for a row missing any of them, which the write skips."""
    words = [row.get(key) for key in keys] if isinstance(row, dict) else [None]
    trimmed = [word.strip() if isinstance(word, str) else "" for word in words]
    return " ".join(trimmed) if all(trimmed) else None


def rows_named_by(datum: str, *keys: str) -> Summary:
    """The summary of a write that creates a record of each row of its list ``datum``: the rows said by the name their
    data ``keys`` give, as a screen lists them before creating them, so the person checks who or what will be created.
    A row without its name counts among the more, never by another of its data; a list that is none stays as sent."""

    def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
        rows = arguments.get(datum)
        return [
            {**field, "value": [_name(row, keys) for row in rows], NAMED: True}
            if field["name"] == datum and isinstance(rows, list)
            else field
            for field in fields
        ]

    return summary


#: The card of an import from a file: its ``rows`` by their ``name``.
by_name = rows_named_by("rows", "name")
