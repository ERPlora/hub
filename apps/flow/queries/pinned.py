"""The data an «Ask the assistant» step fixes (FLOW-F36): why they cannot be saved, and their values in a run."""

from typing import Any

from django.utils.translation import gettext_lazy as _
from live.context import Scope

from apps.flow import document
from apps.flow.models import FlowRun

from .catalog import action_fields, grantable_operations

PINNED_NOT_A_TOOL = _(
    "«%(name)s» has fixed data but the assistant may not use it: add it to what it may use or remove its fixed data."
)
PINNED_NO_INPUT = _("«%(field)s» is no datum of «%(name)s».")
PINNED_EMPTY = _("Give «%(field)s» of «%(name)s» a value, or remove it.")


def fixed_value(raw: Any, data: dict) -> Any:
    """A datum an «Ask the assistant» step fixes, filled in with ``data`` as its prompt is; ``None`` when it is empty
    (a path not found, a text with nothing in it): then its tool is not used."""
    value = document.resolve(raw, data)
    return None if value is None or (isinstance(value, str) and not value.strip()) else value


def pinned_values(run: FlowRun, step: dict, name: str) -> tuple[dict, list[str]]:
    """``(values, empty)``: the data ``step`` fixes for its tool ``name``, filled in with ``run``'s data as its prompt
    is, and the names of those empty now (a path not found, a text with nothing in it)."""
    data = {"input": run.input, "steps": run.outputs}
    values: dict[str, Any] = {}
    empty: list[str] = []
    for field, raw in ((step.get("pinned") or {}).get(name) or {}).items():
        value = fixed_value(raw, data)
        if value is None:
            empty.append(field)
        else:
            values[field] = value
    return values, empty


def pinned_problem(scope: Scope, tools: list[str], pinned: dict[str, dict[str, Any]]) -> str | None:
    """Why the fixed data of an «Ask the assistant» step cannot be saved (the first reason), or ``None``: each is of a
    tool the step may use, names a datum that tool asks for and has a value."""
    for name, fixed in pinned.items():
        op = grantable_operations(scope).get(name)
        if name not in tools or op is None:
            return str(PINNED_NOT_A_TOOL) % {"name": name}
        inputs = {field["name"] for field in action_fields(op)}
        for field, value in fixed.items():
            if field not in inputs:
                return str(PINNED_NO_INPUT) % {"field": field, "name": name}
            if value is None or (isinstance(value, str) and not value.strip()):
                return str(PINNED_EMPTY) % {"field": field, "name": name}
    return None
