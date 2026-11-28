"""What a dataset is, calling the apps' operations as the person who asked, and what a dataset's load did.

An app says what of it travels in a blueprint by the hook ``blueprint_datasets`` of its ``LiveAppConfig``: a list of
:class:`Dataset`, built with these helpers.
"""

import datetime as dt
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

import pydantic
from django.utils.functional import Promise
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


#: The attribute of a ``LiveAppConfig`` that says, for each of its models no dataset carries, why it stays out of the
#: file: ``{"Reservation": "history"}``. Every model of an app travels in one of its datasets or is named here.
STAYS_HOOK = "blueprint_stays"


class Stays(StrEnum):
    """Why a kind of row of an app does not travel in an export of the business."""

    #: What already happened: sales, payments, bookings and visits, clock-ins, runs, logs, messages.
    HISTORY = "history"
    #: The people of the business and what is theirs: the team, their accounts, schedules and time off.
    PEOPLE = "people"
    #: Fiscal data: invoice series and issuers, records for the tax agency, certificates.
    FISCAL = "fiscal"
    #: The app's settings, which no reset erases and every business sets for itself.
    SETTINGS = "settings"
    #: Bound to something outside the business's data: a WhatsApp account, a printer on the local network, a code
    #: already printed, a secret.
    OUTSIDE = "outside"
    #: Kept by the app itself: a counter, an audit trail, a row another one rebuilds.
    INTERNAL = "internal"
    #: Catalogue or configuration that should travel and has no dataset yet.
    PENDING = "pending"


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


@dataclass(frozen=True)
class Dataset:
    """One kind of thing an app lets travel, through that app's own operations."""

    key: str
    label: Promise
    rows: Callable[[OperationContext], list[dict]]
    count: Callable[[OperationContext], int]
    load: Callable[[OperationContext, list[dict], Loaded], None]
    #: Every row's id and how one is removed, to undo a load and to reset the app. Without them what it brings stays,
    #: like the rest of the business's settings: undoing a load neither counts nor removes it, and resetting does not
    #: offer it.
    ids: Callable[[OperationContext], list[str]] | None = None
    remove: Callable[[OperationContext, str], None] | None = None
    #: Personal data (a person's name, phone, email): it travels in a backup only, never in a template.
    personal: bool = False
    #: For rows that show an image: the operations that set one of the library and upload a photo of their own.
    images: tuple[str, str] | None = None
    #: The app's models whose rows travel in this dataset, by class name (a group and its options and links).
    models: tuple[str, ...] = ()

    @property
    def app(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def removable(self) -> bool:
        return self.remove is not None


def call(ctx: OperationContext, operation: str, /, **data: Any) -> Any:
    op = get(operation)
    return op(ctx, op.input(**data))


def pages(ctx: OperationContext, operation: str, /, **params: Any) -> Iterator[Any]:
    """Every row of the list ``operation``, page by page."""
    offset = 0
    while True:
        page = call(ctx, operation, limit=PAGE, offset=offset, **params)
        yield from page.rows
        offset += len(page.rows)
        if not page.rows or offset >= page.total:
            return


def total(ctx: OperationContext, operation: str, /, **params: Any) -> int:
    return call(ctx, operation, limit=1, offset=0, **params).total


def reason(exc: Exception) -> str:
    """What an app said when it refused a row, in one line."""
    if isinstance(exc, pydantic.ValidationError):
        error = exc.errors()[0]
        where = ".".join(str(part) for part in error.get("loc", ()))
        return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))
    if isinstance(exc, OperationError):
        detail = next(iter((exc.fields or {}).values()), "")
        return f"{exc.message} {detail}".strip() if detail and detail not in exc.message else exc.message
    return str(exc)


def text_of(row: dict, key: str) -> str:
    value = row.get(key, "")
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def natural_key(text: str) -> str:
    return text.strip().casefold()


def listed(row: dict, key: str, kind: type) -> list:
    """The items of ``kind`` in the list ``row`` keeps at ``key``; none when it keeps no list there."""
    value = row.get(key)
    return [item for item in value if isinstance(item, kind)] if isinstance(value, list) else []


def given(row: dict, fields: tuple[str, ...]) -> dict:
    """The ``fields`` of ``row`` that have a value."""
    return {name: row[name] for name in fields if row.get(name) not in (None, "")}


def attempt(ctx: OperationContext, loaded: Loaded, label: str, operation: str, /, **data: Any) -> Any:
    """``operation`` on a part of a row just made; one it refuses leaves the row without it, is told, and gives
    ``None``."""
    try:
        return call(ctx, operation, **data)
    except (OperationError, pydantic.ValidationError) as exc:
        loaded.warn(str(ROW_REFUSED) % {"row": label, "reason": reason(exc)})
        return None


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


def create_each(ctx: OperationContext, rows: list[dict], loaded: Loaded, *, name: str, key: Callable[[dict], str],  # noqa: PLR0913
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
            pk = _created(loaded, call(ctx, name, **build(row)))
        except (OperationError, pydantic.ValidationError) as exc:
            loaded.refuse(label(row), reason(exc))
            continue
        existing.add(natural)
        if after is not None:
            after(row, pk)


def ids_of(name: str, **params: Any) -> Callable[[OperationContext], list[str]]:
    """A dataset's ``ids``: those of every row of the list ``name``."""
    return lambda ctx: [str(row.id) for row in pages(ctx, name, **params)]


def count_of(name: str, **params: Any) -> Callable[[OperationContext], int]:
    """A dataset's ``count``: how many rows the list ``name`` has."""
    return lambda ctx: total(ctx, name, **params)


def remover(name: str) -> Callable[[OperationContext, str], None]:
    """A dataset's ``remove``: the operation ``name`` on the row's id."""
    return lambda ctx, pk: call(ctx, name, id=pk)


def as_text(value: Any) -> Any:
    """A date or a time as a file writes it (``2026-12-25``, ``20:00``), also inside a list or a row a row holds (a
    day's opening hours); anything else as it is."""
    if isinstance(value, list):
        return [as_text(item) for item in value]
    if isinstance(value, pydantic.BaseModel):
        return {name: as_text(item) for name, item in value}
    if isinstance(value, dt.time):
        return value.isoformat(timespec="minutes")
    return value.isoformat() if isinstance(value, dt.date) else value


def rows_of(name: str, fields: tuple[str, ...], **params: Any) -> Callable[[OperationContext], list[dict]]:
    """A dataset's ``rows``: the ``fields`` of every row of the list ``name``."""
    return lambda ctx: [{field: as_text(getattr(row, field)) for field in fields} for row in pages(ctx, name, **params)]


def by_name(name: str, create: str, fields: tuple[str, ...], *, named: str = "name"):
    """A dataset's ``load``: each row the business does not have, by its ``named`` field in the list ``name``, made
    with ``create`` from its ``fields``."""

    def load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
        existing = {natural_key(str(getattr(row, named))) for row in pages(ctx, name)}
        create_each(ctx, rows, loaded, name=create, key=lambda row: natural_key(text_of(row, named)),
                    existing=existing, build=lambda row: given(row, fields), label=lambda row: text_of(row, named))

    return load
