"""The tables of the room and their place on the plan (TABLE-F02 to F05, F07)."""

from uuid import UUID

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.table import events
from apps.table.models import BOX, Hold, Table, TableSession, Zone
from apps.table.queries import find_table, find_zone
from apps.table.queries.floor import live_sessions, table_out
from apps.table.schemas import DeletedOut, TableBulkIn, TableIn, TableMoveIn, TablePatchIn, TableRefIn
from apps.table.schemas.floor import TableOut, TablesOut
from apps.table.services.writes import _stamp, settle

#: The free spots of a new table on the plan: a grid of 88 px cells, five a row, 16 px from the edge.
GAP = 16
CELL = BOX + GAP
COLS = 5

NUMBER_TAKEN = _("There is already a table with that number in this zone.")
NUMBERS_TAKEN = _("These numbers are already taken in this zone: %(numbers)s.")
TABLE_HAS_OPEN_SESSION = _(
    "That table has an open check. Close it or move it before deleting the table."
)


def _zone_of(zone_id: UUID | None, said: str | None) -> Zone | None:
    if zone_id is None and not said:
        return None
    return find_zone(zone_id, said)


def _number_taken(number: str, zone: Zone | None, *, except_id=None) -> bool:
    rows = Table.objects.filter(
        is_deleted=False, zone=zone, number__iexact=number.strip()
    )
    return rows.exclude(pk=except_id).exists() if except_id else rows.exists()


def _next_number(zone: Zone | None) -> str:
    """The first free number of the zone, from its count of tables plus one."""
    numbers = {
        n.strip().lower()
        for n in Table.objects.filter(is_deleted=False, zone=zone).values_list(
            "number", flat=True
        )
    }
    candidate = len(numbers) + 1
    while str(candidate) in numbers:
        candidate += 1
    return str(candidate)


def _boxes(zone: Zone | None) -> list[tuple[int, int, int, int]]:
    rows = Table.objects.filter(is_deleted=False, zone=zone).values_list(
        "position_x", "position_y", "width", "height"
    )
    return list(rows)


def _free_spot(
    boxes: list[tuple[int, int, int, int]], width: int, height: int
) -> tuple[int, int]:
    """The first cell of the zone's grid where a ``width`` × ``height`` box covers no table."""
    index = 0
    while True:
        x, y = GAP + (index % COLS) * CELL, GAP + (index // COLS) * CELL
        if not any(
            x < bx + bw and bx < x + width and y < by + bh and by < y + height
            for bx, by, bw, bh in boxes
        ):
            return x, y
        index += 1


def _save_unique(row) -> None:
    """Saves a table; the database's unique number is the net under two creations at once."""
    try:
        with atomic():
            row.save()
    except IntegrityError:
        raise Conflict(str(NUMBER_TAKEN), code="table.number_taken") from None


@operation(
    "table.table.create",
    kind="command",
    permission="table.add_table",
    input=TableIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Add a table to a zone (by the zone's id or name). Without a number it takes the first free "
        "one of the zone; without a position, the first free spot of the plan. Square, for 4, unless told.",
        "risk": "normal",
        "asks": {
            "en": (
                "add table 15 to the terrace",
                "put a new round table for two in the dining room",
            ),
            "es": (
                "añade la mesa 15 en la terraza",
                "pon una mesa redonda nueva para dos en el comedor",
            ),
        },
    },
)
def create_table(ctx: OperationContext, data: TableIn) -> dict:
    zone = _zone_of(data.zone_id, data.zone)
    number = data.number or _next_number(zone)
    if _number_taken(number, zone):
        raise Conflict(str(NUMBER_TAKEN), code="table.number_taken")
    width, height = data.width or BOX, data.height or BOX
    x, y = data.position_x, data.position_y
    if x is None or y is None:
        x, y = _free_spot(_boxes(zone), width, height)
    table = Table(
        zone=zone,
        number=number,
        name=data.name,
        capacity=data.capacity,
        shape=data.shape,
        position_x=x,
        position_y=y,
        width=width,
        height=height,
    )
    _stamp(table, ctx, created=True)
    _save_unique(table)
    record_event(ctx, events.TABLE_CREATED, {"id": str(table.pk)})
    return table_out(table)


@operation(
    "table.table.bulk_create",
    kind="command",
    permission="table.add_table",
    input=TableBulkIn,
    output=TablesOut,
    expose_api=True,
    ai={
        "description": "Create many tables of a zone at once (1 to 100), numbered with a prefix from a first number "
        "(T1…T12), with their seats and shape, in the first free spots of the plan. If a number is taken, none is made.",
        "risk": "normal",
        "asks": {
            "en": (
                "create 10 tables on the terrace, T1 to T10",
                "add twelve tables for four at once",
            ),
            "es": (
                "crea 12 mesas en la terraza, de la T1 a la T12",
                "monta de golpe diez mesas de cuatro en el salón",
            ),
        },
    },
)
def bulk_create_tables(ctx: OperationContext, data: TableBulkIn) -> dict:
    zone = find_zone(data.zone_id, data.zone, lock=True)
    numbers = [
        f"{data.prefix}{data.start_number + index}" for index in range(data.count)
    ]
    taken = [number for number in numbers if _number_taken(number, zone)]
    if taken:
        raise Conflict(
            str(NUMBERS_TAKEN) % {"numbers": ", ".join(taken)},
            code="table.number_taken",
        )
    boxes = _boxes(zone)
    created = []
    for number in numbers:
        x, y = _free_spot(boxes, BOX, BOX)
        boxes.append((x, y, BOX, BOX))
        table = Table(
            zone=zone,
            number=number,
            capacity=data.capacity,
            shape=data.shape,
            position_x=x,
            position_y=y,
        )
        _stamp(table, ctx, created=True)
        _save_unique(table)
        created.append(table)
    record_event(
        ctx, events.TABLE_CREATED, {"ids": [str(table.pk) for table in created]}
    )
    return {"rows": [table_out(table) for table in created]}


@operation(
    "table.table.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_table",
    input=TablePatchIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Change a table (by its id or number): its number, name, seats, shape, zone, whether it is out "
        "of service (blocked) or in use. Only what is sent changes.",
        "risk": "normal",
        "asks": {
            "en": (
                "table 6 now seats six",
                "block table 3, a leg is broken",
                "rename table 9 to Window",
            ),
            "es": (
                "la mesa 6 ahora es para seis",
                "bloquea la mesa 3, que tiene una pata rota",
                "pasa la mesa 9 a la zona de la terraza",
            ),
        },
    },
)
def update_table(ctx: OperationContext, data: TablePatchIn) -> dict:
    table = find_table(data.id, data.table, data.zone, lock=True)
    zone = table.zone
    if data.move_to_zone_id is not None or data.move_to_zone:
        zone = find_zone(data.move_to_zone_id, data.move_to_zone)
    number = data.number if data.number is not None else table.number
    if (number != table.number or zone != table.zone) and _number_taken(
        number, zone, except_id=table.pk
    ):
        raise Conflict(str(NUMBER_TAKEN), code="table.number_taken")
    table.zone, table.number = zone, number
    for field in ("name", "capacity", "shape", "blocked", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(table, field, value)
    _stamp(table, ctx)
    _save_unique(table)
    record_event(ctx, events.TABLE_UPDATED, {"id": str(table.pk)})
    return table_out(table)


@operation(
    "table.table.move",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_table",
    input=TableMoveIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Place a table on its zone's plan (pixels from the top-left corner), and resize its box.",
        "risk": "normal",
        "asks": {
            "en": (
                "move table 4 to the left on the floor plan",
                "make table 2 bigger on the plan",
            ),
            "es": (
                "coloca la mesa 4 más a la izquierda en el plano",
                "haz más grande la mesa 2 en el plano",
            ),
        },
    },
)
def move_table(ctx: OperationContext, data: TableMoveIn) -> dict:
    table = find_table(data.id, None, lock=True)
    table.position_x, table.position_y = data.position_x, data.position_y
    if data.width is not None:
        table.width = data.width
    if data.height is not None:
        table.height = data.height
    _stamp(table, ctx)
    table.save()
    record_event(ctx, events.TABLE_UPDATED, {"id": str(table.pk)})
    return table_out(table)


@operation(
    "table.table.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.delete_table",
    input=TableRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a table (by its id or number): it leaves the plan and the lists, its history of checks "
        "stays. A table with an open check is refused.",
        "risk": "high",
        "asks": {
            "en": (
                "delete table 12, we got rid of it",
                "remove table 8 from the room",
            ),
            "es": (
                "borra la mesa 12, ya no la tenemos",
                "elimina la mesa 8 del salón",
            ),
        },
    },
)
def delete_table(ctx: OperationContext, data: TableRefIn) -> dict:
    table = find_table(data.id, data.table, data.zone, lock=True)
    settle(TableSession.objects.filter(table=table))
    if live_sessions().filter(table=table).exists():
        raise Conflict(str(TABLE_HAS_OPEN_SESSION), code="table.table_has_open_session")
    now = timezone.now()
    table.is_deleted, table.is_active, table.deleted_at = True, False, now
    _stamp(table, ctx)
    table.save()
    table.holds.filter(status=Hold.Status.HELD).update(
        status=Hold.Status.RELEASED, label="", updated_at=now
    )
    record_event(ctx, events.TABLE_DELETED, {"id": str(table.pk)})
    return {"id": table.pk}
