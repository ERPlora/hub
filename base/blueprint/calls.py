"""Calling the apps' operations as the person who asked, and what a dataset's load did."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import pydantic
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError
from live.operations import get

#: The problems told per dataset: the first ones say what to fix; the count says how many.
MAX_PROBLEMS = 20
#: A list operation's page (``limit`` ≤ 100, every app's lists).
PAGE = 100

NO_NAME = _("A row has no name.")
ROW_REFUSED = _("«%(row)s»: %(reason)s")


@dataclass
class Loaded:
    """What a dataset's load did: the ids it created (for undo), the rows already there, and the ones refused."""

    created: list[str] = field(default_factory=list)
    already: int = 0
    failed: int = 0
    problems: list[str] = field(default_factory=list)
    #: The photos the blueprint carries, for the rows that name one (``Bundle.media``).
    media: dict[str, bytes] = field(default_factory=dict)

    def refuse(self, row: str, reason: str, *, counted: bool = True) -> None:
        if counted:
            self.failed += 1
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(str(ROW_REFUSED) % {"row": row, "reason": reason} if row else reason)

    def warn(self, text: str) -> None:
        if len(self.problems) < MAX_PROBLEMS:
            self.problems.append(text)


def _call(ctx: OperationContext, operation: str, /, **data: Any) -> Any:
    op = get(operation)
    return op(ctx, op.input(**data))


def _pages(ctx: OperationContext, operation: str, /, **params: Any) -> Iterator[Any]:
    """Every row of the list ``operation``, page by page."""
    offset = 0
    while True:
        page = _call(ctx, operation, limit=PAGE, offset=offset, **params)
        yield from page.rows
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def _total(ctx: OperationContext, operation: str, /, **params: Any) -> int:
    return _call(ctx, operation, limit=1, offset=0, **params).total


def _reason(exc: Exception) -> str:
    """What an app said when it refused a row, in one line."""
    if isinstance(exc, pydantic.ValidationError):
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error.get("loc", ()))
        return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))
    if isinstance(exc, OperationError):
        detail = next(iter((exc.fields or {}).values()), "")
        return f"{exc.message} {detail}".strip() if detail and detail not in exc.message else exc.message
    return str(exc)


def _text(row: dict, key: str) -> str:
    value = row.get(key, "")
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _key(text: str) -> str:
    return text.strip().casefold()


def _money(cents: Any) -> str:
    """Cents as a price cell the import reads (``8.50``)."""
    if isinstance(cents, bool) or not isinstance(cents, int):
        return str(cents)
    return f"{Decimal(cents) / 100:.2f}"


def _quantity(value: Any, *, blank_zero: bool = False) -> str:
    """A quantity as text, exact and without trailing zeros (``24``, ``0.5``); zero left blank if ``blank_zero``."""
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if blank_zero and not number:
        return ""
    text = format(number.normalize(), "f")
    return "0" if text in {"-0", ""} else text


def _created(loaded: Loaded, result: Any) -> str:
    pk = str(result.id)
    loaded.created.append(pk)
    return pk


def _create_each(ctx: OperationContext, rows: list[dict], loaded: Loaded, *, name: str, key: Callable[[dict], str],  # noqa: PLR0913
                 existing: set[str], build: Callable[[dict], dict], label: Callable[[dict], str],
                 after: Callable[[dict, str], None] | None = None) -> None:
    """Create each row by ``name`` unless its natural ``key`` is already there; a refused row fails alone. ``after``
    runs for each row created, with its id (its image)."""
    for row in rows:
        natural = key(row)
        if not natural:
            loaded.refuse("", str(NO_NAME))
            continue
        if natural in existing:
            loaded.already += 1
            continue
        try:
            pk = _created(loaded, _call(ctx, name, **build(row)))
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.refuse(label(row), _reason(exc))
            continue
        existing.add(natural)
        if after is not None:
            after(row, pk)
