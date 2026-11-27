"""What of Reservations travels in an export of the business (BASE-F35): the book's time slots and its blocked days,
read with Reservations' own lists and written with its own creates. A slot is named by its weekday and its start, a
blocked day by its date and its start. The reservations and the waiting list never travel: they already happened."""

import datetime as dt

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, count_of, create_each, given, ids_of, pages, remover, text_of

SLOT_FIELDS = ("day_of_week", "start_time", "end_time", "max_reservations", "max_covers")
BLOCK_FIELDS = ("date", "reason", "is_full_day", "blocked_from", "blocked_until")


def _text(value):
    """A date or a time as the file writes it (``2026-12-25``, ``20:00``); anything else as it is."""
    if isinstance(value, dt.time):
        return value.isoformat(timespec="minutes")
    return value.isoformat() if isinstance(value, dt.date) else value


def _slot_key(row: dict) -> str:
    return f"{text_of(row, 'day_of_week')}\x00{text_of(row, 'start_time')[:5]}"


def _block_key(row: dict) -> str:
    return f"{text_of(row, 'date')}\x00{text_of(row, 'blocked_from')[:5]}"


def _rows(ctx: OperationContext, operation: str, fields: tuple[str, ...]) -> list[dict]:
    return [{name: _text(getattr(row, name)) for name in fields} for row in pages(ctx, operation)]


def _slot_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_slot_key(row) for row in _rows(ctx, "reservation.time_slot.list", SLOT_FIELDS)}
    create_each(ctx, rows, loaded, name="reservation.time_slot.create", key=_slot_key, existing=existing,
                build=lambda row: given(row, SLOT_FIELDS), label=lambda row: _slot_key(row).replace("\x00", " · "))


def _block_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_block_key(row) for row in _rows(ctx, "reservation.blocked_date.list", BLOCK_FIELDS)}
    create_each(ctx, rows, loaded, name="reservation.blocked_date.create", key=_block_key, existing=existing,
                build=lambda row: given(row, BLOCK_FIELDS), label=lambda row: text_of(row, "date"))


DATASETS = [
    Dataset(
        key="reservation.time_slot",
        label=_("Booking time slots"),
        rows=lambda ctx: _rows(ctx, "reservation.time_slot.list", SLOT_FIELDS),
        ids=ids_of("reservation.time_slot.list"),
        count=count_of("reservation.time_slot.list"),
        load=_slot_load,
        remove=remover("reservation.time_slot.delete"),
        models=("TimeSlot",),
    ),
    Dataset(
        key="reservation.blocked_date",
        label=_("Blocked days"),
        rows=lambda ctx: _rows(ctx, "reservation.blocked_date.list", BLOCK_FIELDS),
        ids=ids_of("reservation.blocked_date.list"),
        count=count_of("reservation.blocked_date.list"),
        load=_block_load,
        remove=remover("reservation.blocked_date.delete"),
        models=("BlockedDate",),
    ),
]
