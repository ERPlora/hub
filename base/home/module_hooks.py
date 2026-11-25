"""Running a module's hook: its query, by name, as the person of the request, and the first row it gives."""

import logging
from collections.abc import Mapping
from typing import Any

from live.context import OperationContext
from live.operations import get

# Its lines keep the name they always had, whichever module of the package writes them.
logger = logging.getLogger("base.home")


def first_row(result: Mapping[str, Any]) -> dict | None:
    """The row a step or a counter reads: the first of ``rows``/``items`` in a list, the object itself otherwise."""
    for name in ("rows", "items"):
        rows = result.get(name)
        if isinstance(rows, list):
            return rows[0] if rows else None
    return dict(result)


def run_hook(ctx: OperationContext, operation: str, params: Mapping[str, Any]) -> dict | None:
    """The first row of ``operation`` run with ``params`` as the person of ``ctx``.

    Raises whatever the operation raises; the caller leaves the hook out and logs it (``hook_failed``).
    """
    op = get(operation)
    return first_row(op(ctx, op.input.model_validate(dict(params))).model_dump(mode="json"))


def hook_failed(key: str, operation: str, error: BaseException | None = None) -> None:
    """Logs the hook left out with the traceback of ``error`` (outside its ``except``), else of the one handled now."""
    logger.warning("Home: %s left out, its query %s failed.", key, operation, exc_info=error or True)
