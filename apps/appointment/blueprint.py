"""What of Appointments travels in an export of the business (BASE-F35): the agenda's blocks still to come, the whole
business's and each professional's by the professional's name, read and written with Appointments' own operations. A
block is named by its title, its start and its professional; one whose professional the business that loads it does not
have is told and left out. The appointments, the recurring series and the blocks that already ended never travel: they
already happened."""

import datetime as dt

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from base.blueprint.calls import Dataset, Loaded, as_text, count_of, create_each, given, ids_of, natural_key, pages
from base.blueprint.calls import remover, text_of

UPCOMING = "appointment.blocked_time.list_upcoming"
BLOCK_FIELDS = ("title", "block_type", "start", "end", "all_day", "staff", "reason")


def _block_row(row) -> dict:
    # A whole-day block ends at the midnight after its last day; its create takes that last day.
    end = row.end - dt.timedelta(days=1) if row.all_day else row.end
    return {
        "title": row.title,
        "block_type": row.block_type,
        "start": as_text(row.start),
        "end": as_text(end),
        "all_day": row.all_day,
        "staff": row.staff_name,
        "reason": row.reason,
    }


def _block_rows(ctx: OperationContext) -> list[dict]:
    return [_block_row(row) for row in pages(ctx, UPCOMING)]


def _block_key(row: dict) -> str:
    return "\x00".join((natural_key(text_of(row, "title")), text_of(row, "start"), natural_key(text_of(row, "staff"))))


def _block_load(ctx: OperationContext, rows: list[dict], loaded: Loaded) -> None:
    existing = {_block_key(row) for row in _block_rows(ctx)}
    create_each(ctx, rows, loaded, name="appointment.blocked_time.create",
                key=lambda row: _block_key(row) if text_of(row, "title") else "", existing=existing,
                build=lambda row: given(row, BLOCK_FIELDS), label=lambda row: text_of(row, "title"))  # fmt: skip


DATASETS = [
    Dataset(
        key="appointment.blocked_time",
        label=_("Agenda blocks"),
        rows=_block_rows,
        ids=ids_of(UPCOMING),
        count=count_of(UPCOMING),
        load=_block_load,
        remove=remover("appointment.blocked_time.delete"),
        models=("BlockedTime",),
    ),
]
