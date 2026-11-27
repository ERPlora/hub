"""The card of a write that creates several records at once (``ai={"summary": …}``) — an import from a file, people
or services the person dictates —: its rows by the name each one gives and, beside them, what they share."""

from collections.abc import Callable
from typing import Any

from django.utils.translation import gettext
from live.assistant import NAMED
from live.context import OperationContext

Summary = Callable[[OperationContext, dict, list[dict]], list[dict]]


def _name(row: Any, keys: tuple[str, ...]) -> str | None:
    """The name a row gives by its data ``keys``, each trimmed as the write keeps it and joined as a name is written
    («Carla» and «Ruiz QA», «Carla Ruiz QA»); none for a row missing any of them, which the write skips."""
    words = [row.get(key) for key in keys] if isinstance(row, dict) else [None]
    trimmed = [word.strip() if isinstance(word, str) else "" for word in words]
    return " ".join(trimmed) if all(trimmed) else None


def _shared(said_rows: Any, datum: str) -> list[str]:
    """What the rows say of ``datum``, as the card said each (a record by its name, never by an id: one it cannot name
    it leaves out), in their order and without repeats."""
    said = [row.get(datum) for row in said_rows if isinstance(row, dict)] if isinstance(said_rows, list) else []
    return list(dict.fromkeys(text for text in said if isinstance(text, str) and text.strip()))


def rows_named_by(datum: str, *keys: str, beside: dict[str, str] | None = None) -> Summary:
    """The summary of a write that creates a record of each row of its list ``datum``: the rows said by the name their
    data ``keys`` give, as a screen lists them before creating them, so the person checks who or what will be created.
    A row without its name counts among the more, never by another of its data; a list that is none stays as sent.
    Each datum of ``beside`` the rows carry (a tax category, a category) is said after them on a line of its own, under
    its label (a title to translate), once each: what the names alone would hide."""

    def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
        rows = arguments.get(datum)
        if not isinstance(rows, list):
            return fields
        said_rows = next((field["value"] for field in fields if field["name"] == datum), None)
        shared = [
            {"name": name, "label": gettext(label), "kind": "list", "value": values, NAMED: True}
            for name, label in (beside or {}).items()
            if (values := _shared(said_rows, name))
        ]
        names = [_name(row, keys) for row in rows]
        named = [{**field, "value": names, NAMED: True} if field["name"] == datum else field for field in fields]
        return [*named, *shared]

    return summary


#: The card of an import from a file: its ``rows`` by their ``name``.
by_name = rows_named_by("rows", "name")
