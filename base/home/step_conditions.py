"""When a step's conditions (``configured_when``) pass on the first row of its query, as the old hub had it."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from live.meta import SetupCheck


def truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text != "0" and text.lower() != "false"
    if isinstance(value, list):
        return bool(value)
    return True


def as_text(value: Any) -> str:
    """A value as the old hub compared it with ``equals``: lax, as text (``2`` equals ``"2"``)."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value)


def passes(row: Mapping[str, Any], check: SetupCheck) -> bool:
    value = row.get(check.field)
    if check.truthy is not None:
        return truthy(value) == check.truthy
    if check.equals is not None:
        return as_text(value) == as_text(check.equals)
    return False  # a half-written condition never ticks the step as done


def is_configured(row: Mapping[str, Any] | None, checks: Sequence[SetupCheck]) -> bool:
    return row is not None and all(passes(row, check) for check in checks)
