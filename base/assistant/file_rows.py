"""The card of an import from a file (``ai={"summary": file_rows.by_name}``): its rows by the name each one gives."""

from typing import Any

from live.assistant import NAMED
from live.context import OperationContext


def _name(row: Any) -> str | None:
    """The name a row gives, trimmed as the import keeps it; none for a row without one, which the import skips."""
    name = row.get("name") if isinstance(row, dict) else None
    if not isinstance(name, str):
        return None
    return name.strip() or None


def by_name(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    """The card's ``rows`` said by their names, as the screen lists them before importing: the person checks what will
    be created. A row without a name counts among the more, never by another of its cells."""
    return [
        {**field, "value": [_name(row) for row in arguments["rows"]], NAMED: True}
        if field["name"] == "rows" and isinstance(arguments.get("rows"), list)
        else field
        for field in fields
    ]
