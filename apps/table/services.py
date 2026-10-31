"""Write operations of the table app: drawing the room (zones, tables), serving it (seating, closing,
moving, joining and splitting the checks of its tables), the holds and the settings.

Each one is one transaction with its events in the outbox. The check of a table is an open check of
Sales: seating opens it (``sale.order.open``) or retitles the one brought (``sale.order.set_label``);
a transfer and a restore retitle it; a merge joins the two checks (``sale.order.merge``); a split
divides it (``sale.order.split``); closing a table whose check is empty voids it (``sale.order.void``, which Sales allows on an empty
check to whoever builds checks).
Sales' operations are called by name, with the caller's own session and inside this transaction: if
Sales refuses, nothing of the table changes either.

Concurrency: a write that seats a check locks the table first (``select_for_update``) and checks it is
still free under the lock, so two waiters seating the same table at once leave one check; a write on a
check locks the check. Phase 1 has no relay: before deciding, a write closes the checks whose check of
Sales already ended (``settle``), as the reads already show them.
"""

import datetime as dt
import logging
from uuid import UUID

from django.db import IntegrityError
from django.db.models import Max
from django.utils import timezone, translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound, OperationError
from live.operations import UnknownOperation, atomic, get, operation
from live.outbox import record_event

from apps.customer.queries import find_customer
from apps.sale.models import Order
from apps.table import events
from apps.table.models import (
    ACTOR_MAX_LENGTH,
    BOX,
    Hold,
    SessionMove,
    Table,
    TableSession,
    TableSettings,
    Zone,
)
from apps.table.queries import (
    HOLD_NOT_FOUND,
    business_zone,
    check_label,
    current_settings,
    ended_orders,
    find_session,
    find_table,
    find_zone,
    hold_row,
    live_sessions,
    order_is_open,
    reserving_holds,
    seatable,
    session_out,
    settings_row,
    table_out,
    zone_rows,
    zones_now,
)
from apps.table.schemas import (
    ByIdIn,
    ByOrderIn,
    ClosedOut,
    CustomerErasedIn,
    DeletedOut,
    ExpiredOut,
    HoldOut,
    HoldPlaceIn,
    HoldReleaseIn,
    HoldsChangedOut,
    NoIn,
    ReservationStatusIn,
    ReservationUpdatedIn,
    SessionCloseIn,
    SessionGuestsIn,
    SessionLinkOrderIn,
    SessionMergeIn,
    SessionOpenIn,
    SessionOut,
    SessionRefIn,
    SessionRestoreIn,
    SessionSplitIn,
    SessionTransferIn,
    SettingsIn,
    SettingsOut,
    SplitOut,
    TableBulkIn,
    TableIn,
    TableMoveIn,
    TableOut,
    TablePatchIn,
    TableRefIn,
    TablesOut,
    ZoneIn,
    ZoneOut,
    ZonePatchIn,
    ZoneRefIn,
)

logger = logging.getLogger(__name__)

S = TableSession.Status
#: The checks still alive: seated (open) or parked; Sales ending their check ends them.
LIVE = [S.OPEN, S.PARKED]

#: The platform's own writes (reactions, the sweep): the system has «*»; no role is given this one.
SYSTEM = "table.system"
#: The free spots of a new table on the plan: a grid of 88 px cells, five a row, 16 px from the edge.
GAP = 16
CELL = BOX + GAP
COLS = 5
#: How long a reservation holds its table when it does not say (the old module's default).
DEFAULT_RESERVATION_MINUTES = 120

ZONE_NAME_TAKEN = _("There is already a zone with that name.")
ZONE_HAS_TABLES = _(
    "That zone still has tables. Move them to another zone or delete them first."
)
NUMBER_TAKEN = _("There is already a table with that number in this zone.")
NUMBERS_TAKEN = _("These numbers are already taken in this zone: %(numbers)s.")
TABLE_HAS_OPEN_SESSION = _(
    "That table has an open check. Close it or move it before deleting the table."
)
TABLE_NOT_AVAILABLE = _(
    "That table cannot be seated right now: it is taken, out of service or no longer in use."
)
SESSION_NOT_ACTIVE = _(
    "That check is not open: it does not exist in this business, or it has already been closed, "
    "transferred, merged or parked."
)
SESSION_NOT_PARKED = _(
    "That check is not parked: it does not exist in this business, or it is already seated at a table."
)
SESSION_STILL_OPEN = _("That check is still open: close it before deleting it.")
BILL_OPEN = _(
    "This table's bill is still open in Sales: charge it, move it to another table or delete it from the till."
)
BILL_MISMATCH = _("This table's bill has changed. Reload the list and try again.")
ORDER_NOT_OPEN = _("That check is no longer open in Sales.")
ORDER_ELSEWHERE = _("That check is already at table %(table)s.")
NOTHING_TO_MERGE = _("That table has no other open check to merge with.")
SALE_UNAVAILABLE = _(
    "Sales is not available in this business: the table's check cannot be opened or changed."
)
RED_BEFORE_AMBER = _("The red warning cannot come before the amber one.")


# ── Who acts ─────────────────────────────────────────────────────────────────────────────────────


def actor_label(ctx: OperationContext) -> str:
    """Who acts, as a person reads it: a user's name (or e-mail, or username); the system's own label."""
    who = ctx.actor
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        label = who.get_full_name() or getattr(who, "email", "") or who.get_username()
    else:
        label = str(who)
    return label[:ACTOR_MAX_LENGTH]


def actor_id(ctx: OperationContext) -> str:
    who = ctx.actor
    if who is None:
        return ""
    pk = getattr(who, "pk", None)
    return str(pk if pk is not None else who)[:64]


def _stamp(row, ctx: OperationContext, *, created: bool = False) -> None:
    row.updated_by = actor_label(ctx)
    if created:
        row.created_by = row.updated_by


# ── Sales and Customers, by their operations ─────────────────────────────────────────────────────


def call_app(ctx: OperationContext, name: str, data: dict):
    """Runs another app's operation ``name`` with the caller's session, in this transaction."""
    try:
        op = get(name)
    except UnknownOperation:
        raise Conflict(str(SALE_UNAVAILABLE), code="table.sale_unavailable") from None
    try:
        return op(ctx, op.input.model_validate(data))
    except AppInactive:
        raise Conflict(str(SALE_UNAVAILABLE), code="table.sale_unavailable") from None


def title(ctx: OperationContext, table: Table) -> str:
    """The title of a table's check in Sales («Table 4», «Mesa 4»), in the language of whoever acts."""
    with translation.override(ctx.language):
        return gettext("Table %(number)s") % {"number": table.number}


def retitle(ctx: OperationContext, order_id: UUID | None, table: Table) -> None:
    if order_is_open(order_id):
        call_app(
            ctx,
            "sale.order.set_label",
            {"order_id": str(order_id), "label": title(ctx, table)},
        )


# ── The checks: settle, stretches, holds ─────────────────────────────────────────────────────────


def settle(sessions) -> None:
    """Closes the open and parked checks of ``sessions`` whose check of Sales already ended (charged in
    full or voided), at the hour Sales closed it: what the reads already show (no relay in phase 1). A
    parked one has no stretch at a table left to end; it stays without a table."""
    ending = list(
        sessions.filter(status__in=LIVE, is_deleted=False, order_id__in=ended_orders())
    )
    if not ending:
        return
    closed = dict(
        Order.objects.filter(pk__in=[s.order_id for s in ending]).values_list(
            "pk", "closed_at"
        )
    )
    for session in ending:
        at = closed.get(session.order_id) or timezone.now()
        session.status = S.CLOSED
        session.closed_at = at
        session.save(update_fields=["status", "closed_at", "updated_at"])
        _release(session, SessionMove.Release.CLOSED, at)


def _settled(session: TableSession) -> TableSession:
    settle(TableSession.objects.filter(pk=session.pk))
    session.refresh_from_db()
    return session


def _open_session(data, *, lock: bool = True) -> TableSession:
    """The check the input names, locked and still open; else 409 ``table.session_not_active``."""
    session = _settled(find_session(data.id, data.table, data.zone, lock=lock))
    if session.status != S.OPEN:
        raise Conflict(str(SESSION_NOT_ACTIVE), code="table.session_not_active")
    return session


def _seatable_table(
    table_id, said, zone_said, now, *, occupied_ok: bool = False
) -> Table:
    """The table named, locked; refused unless a check may sit there now."""
    table = find_table(table_id, said, zone_said, lock=True)
    settle(TableSession.objects.filter(table=table))
    if not seatable(table, now, occupied_ok=occupied_ok):
        raise Conflict(str(TABLE_NOT_AVAILABLE), code="table.table_not_available")
    return table


def _seat_at(
    session: TableSession,
    table: Table,
    reason: str,
    now: dt.datetime,
    reservation_id: UUID | None = None,
) -> None:
    SessionMove.objects.create(
        session=session, table=table, assigned_at=now, assignment_reason=reason
    )
    _consume_holds(table, now, reservation_id)


def _release(session: TableSession, reason: str, now: dt.datetime) -> None:
    SessionMove.objects.filter(session=session, released_at__isnull=True).update(
        released_at=now, release_reason=reason
    )


def _seating_holds(table: Table, now: dt.datetime, reservation_id: UUID | None):
    """The holds a party sitting at ``table`` now spends: the ones already painting it Reserved (never a later
    one) and, when the party is a reservation's, only that reservation's (a later party's hold stays)."""
    holds = reserving_holds(now).filter(table=table)
    if reservation_id is not None:
        holds = holds.filter(
            source=Hold.Source.RESERVATION, source_ref=str(reservation_id)
        )
    return holds


def _consume_holds(
    table: Table, now: dt.datetime, reservation_id: UUID | None = None
) -> None:
    _seating_holds(table, now, reservation_id).update(
        status=Hold.Status.CONSUMED, label="", updated_at=now
    )


def _event(ctx: OperationContext, name: str, session: TableSession, **more) -> None:
    payload = {
        "id": str(session.pk),
        "table_id": str(session.table_id) if session.table_id else None,
        **more,
    }
    record_event(ctx, name, payload)


# ── Zones ────────────────────────────────────────────────────────────────────────────────────────


def _zone_name_taken(name: str, *, except_id=None) -> bool:
    rows = Zone.objects.filter(is_deleted=False, name__iexact=name.strip())
    return rows.exclude(pk=except_id).exists() if except_id else rows.exists()


def _save_zone(zone: Zone) -> None:
    """Saves a zone; the database's unique name is the net under two writes at once (a 409, never a 500)."""
    try:
        with atomic():
            zone.save()
    except IntegrityError:
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken") from None


def _zone_out(zone: Zone) -> dict:
    return zone_rows([zones_now(timezone.now()).get(pk=zone.pk)])[0]


@operation(
    "table.zone.create",
    kind="command",
    permission="table.add_zone",
    input=ZoneIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Create a zone of the room (dining room, terrace, bar…); it goes last unless told its order.",
        "risk": "normal",
    },
)
def create_zone(ctx: OperationContext, data: ZoneIn) -> dict:
    if _zone_name_taken(data.name):
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken")
    order = data.sort_order
    if order is None:
        last = Zone.objects.filter(is_deleted=False).aggregate(last=Max("sort_order"))[
            "last"
        ]
        order = 0 if last is None else last + 1
    zone = Zone(
        name=data.name, description=data.description, color=data.color, sort_order=order
    )
    _stamp(zone, ctx, created=True)
    _save_zone(zone)
    record_event(ctx, events.ZONE_CREATED, {"id": str(zone.pk)})
    return _zone_out(zone)


@operation(
    "table.zone.update",
    kind="command",
    permission="table.change_zone",
    input=ZonePatchIn,
    output=ZoneOut,
    expose_api=True,
    ai={
        "description": "Rename a zone or change its description, colour, order or whether it is in service (an "
        "inactive zone leaves the service view). Only what is sent changes.",
        "risk": "normal",
    },
)
def update_zone(ctx: OperationContext, data: ZonePatchIn) -> dict:
    zone = find_zone(data.id, data.zone, lock=True)
    if data.name is not None and _zone_name_taken(data.name, except_id=zone.pk):
        raise Conflict(str(ZONE_NAME_TAKEN), code="table.zone_name_taken")
    for field in ("name", "description", "color", "sort_order", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(zone, field, value)
    _stamp(zone, ctx)
    _save_zone(zone)
    record_event(ctx, events.ZONE_UPDATED, {"id": str(zone.pk)})
    return _zone_out(zone)


@operation(
    "table.zone.delete",
    kind="command",
    permission="table.delete_zone",
    input=ZoneRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete an empty zone (a zone with tables is refused: move or delete them first).",
        "risk": "high",
    },
)
def delete_zone(ctx: OperationContext, data: ZoneRefIn) -> dict:
    zone = find_zone(data.id, data.zone, lock=True)
    if Table.objects.filter(zone=zone, is_deleted=False).exists():
        raise Conflict(str(ZONE_HAS_TABLES), code="table.zone_has_tables")
    zone.is_deleted, zone.is_active, zone.deleted_at = True, False, timezone.now()
    _stamp(zone, ctx)
    zone.save()
    record_event(ctx, events.ZONE_DELETED, {"id": str(zone.pk)})
    return {"id": zone.pk}


# ── Tables ───────────────────────────────────────────────────────────────────────────────────────


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
    """The first free number of the zone, from its count of tables plus one (the old canvas' rule)."""
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
    permission="table.change_table",
    input=TablePatchIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Change a table (by its id or number): its number, name, seats, shape, zone, whether it is out "
        "of service (blocked) or in use. Only what is sent changes.",
        "risk": "normal",
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
    permission="table.change_table",
    input=TableMoveIn,
    output=TableOut,
    expose_api=True,
    ai={
        "description": "Place a table on its zone's plan (pixels from the top-left corner), and resize its box.",
        "risk": "normal",
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
    permission="table.delete_table",
    input=TableRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a table (by its id or number): it leaves the plan and the lists, its history of checks "
        "stays. A table with an open check is refused.",
        "risk": "high",
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


# ── Seating and serving ──────────────────────────────────────────────────────────────────────────


def _bring_order(ctx: OperationContext, order_id: UUID, table: Table) -> None:
    """Checks the open check of Sales brought to ``table`` is open and at no other table, and retitles it.

    The check of Sales is locked first: two tables bringing it at once go in turn, and the second is told
    where it is (a 409, never the database's unique index as a 500)."""
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None or order.status != Order.Status.OPEN:
        raise Conflict(str(ORDER_NOT_OPEN), code="table.order_not_open")
    holder = (
        TableSession.objects.filter(
            order_id=order_id, status__in=[S.OPEN, S.PARKED], is_deleted=False
        )
        .select_related("table", "table__zone")
        .first()
    )
    if holder is not None:
        where = check_label(holder)
        raise Conflict(
            str(ORDER_ELSEWHERE) % {"table": where}, code="table.order_elsewhere"
        )
    retitle(ctx, order_id, table)


def _put_customer(ctx: OperationContext, order_id: UUID, customer_id: UUID | None, said: str | None) -> None:
    """Puts the customer on the table's check (Customers' link). If Customers refuses (no such card, several
    match, not allowed), the table is seated all the same and the check stays without one (TABLE-F32): the
    reply says so with its empty customer."""
    try:
        with atomic():
            customer = find_customer(customer_id, said)
            call_app(ctx, "customer.order.link", {"order_id": str(order_id), "customer_id": str(customer.pk)})
    except OperationError as refusal:
        logger.info("table: seated without the customer (%s)", refusal.code)


@operation(
    "table.session.open",
    kind="command",
    permission="table.add_session",
    input=SessionOpenIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Seat a party at a free or reserved table («seat 3 at table 4»): its check opens in Sales titled "
        "with the table. Without guests, the reservation's or the table's seats. Optionally bring an open check of "
        "Sales to the table, and put a customer (by name or phone) on the check.",
        "risk": "normal",
        # Done by the waiter with the party in front, never by an automation (TABLE-F10).
        "in_person": True,
    },
)
def open_session(ctx: OperationContext, data: SessionOpenIn) -> dict:
    now = timezone.now()
    table = _seatable_table(data.table_id, data.table, data.zone, now)
    guests = data.guests_count
    if guests is None:
        hold = (
            _seating_holds(table, now, data.reservation_id)
            .filter(party_size__gt=0)
            .order_by("held_from", "id")
            .first()
        )
        guests = hold.party_size if hold else table.capacity
    if data.order_id is not None:
        _bring_order(ctx, data.order_id, table)
        order_id = data.order_id
    else:
        order_id = call_app(ctx, "sale.order.open", {"label": title(ctx, table)}).id
    session = TableSession(
        table=table,
        order_id=order_id,
        guests_count=guests,
        notes=data.notes,
        waiter_id=actor_id(ctx),
        waiter_name=actor_label(ctx),
        opened_at=now,
    )
    _stamp(session, ctx, created=True)
    session.save()
    _seat_at(session, table, SessionMove.Reason.OPENED, now, data.reservation_id)
    if data.customer_id or data.customer:
        _put_customer(ctx, order_id, data.customer_id, data.customer)
    _event(
        ctx, events.SESSION_OPENED, session, order_id=str(order_id), guests_count=guests
    )
    return session_out(session)


@operation(
    "table.session.close",
    kind="command",
    permission="table.change_session",
    input=SessionCloseIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Close a table's check by hand and free the table if nothing else sits there. A check with "
        "something ordered still open in Sales is refused (charge it, move it or delete it first); an empty one is "
        "voided in Sales. Ask first.",
        "risk": "high",
    },
)
def close_session(ctx: OperationContext, data: SessionCloseIn) -> dict:
    session = _open_session(data)
    if data.order_id is not None and data.order_id != session.order_id:
        raise Conflict(str(BILL_MISMATCH), code="table.session_bill_mismatch")
    if session.order_id is not None:
        order = Order.objects.select_for_update().filter(pk=session.order_id).first()
        if order is not None and order.status == Order.Status.OPEN:
            if order.lines.live().exists():
                raise Conflict(str(BILL_OPEN), code="table.session_bill_open")
            # An empty check (no lines, no charges): Sales lets whoever builds checks void it, so the
            # waiter closes the table without a manager. Always with the caller's own session: Tables
            # never widens anybody's permissions.
            call_app(ctx, "sale.order.void", {"order_id": str(order.pk)})
    now = timezone.now()
    session.status, session.closed_at = S.CLOSED, now
    if data.notes:
        session.notes = (
            f"{session.notes}\n{data.notes}" if session.notes else data.notes
        )
    _stamp(session, ctx)
    session.save()
    _release(session, SessionMove.Release.CLOSED, now)
    _event(
        ctx,
        events.SESSION_CLOSED,
        session,
        order_id=str(session.order_id) if session.order_id else None,
    )
    return session_out(session)


@operation(
    "table.session.transfer",
    kind="command",
    permission="table.transfer_session",
    input=SessionTransferIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Move a table's check to a free or reserved table («move table 4 to 6»): same check of Sales "
        "(retitled), guests, waiter and notes; the old table frees if nothing else sits there. Ask first.",
        "risk": "high",
    },
)
def transfer_session(ctx: OperationContext, data: SessionTransferIn) -> dict:
    source = _open_session(data)
    now = timezone.now()
    target = _seatable_table(data.to_table_id, data.to_table, data.to_zone, now)
    order_id = source.order_id
    source.status, source.closed_at, source.order_id = S.TRANSFERRED, now, None
    _stamp(source, ctx)
    source.save()
    _release(source, SessionMove.Release.TRANSFERRED, now)
    moved = TableSession(
        table=target,
        order_id=order_id,
        guests_count=source.guests_count,
        notes=source.notes,
        waiter_id=source.waiter_id,
        waiter_name=source.waiter_name,
        opened_at=source.opened_at,
        transferred_from=source,
    )
    _stamp(moved, ctx, created=True)
    moved.save()
    _seat_at(moved, target, SessionMove.Reason.TRANSFERRED, now)
    retitle(ctx, order_id, target)
    _event(
        ctx,
        events.SESSION_TRANSFERRED,
        moved,
        from_id=str(source.pk),
        from_table_id=str(source.table_id),
        order_id=str(order_id) if order_id else None,
    )
    return session_out(moved)


def _merge_target(data: SessionMergeIn, source: TableSession) -> TableSession:
    if data.into_session_id is not None:
        target = _settled(find_session(data.into_session_id, None))
    else:
        table = find_table(data.into_table_id, data.into_table, data.into_zone)
        settle(TableSession.objects.filter(table=table))
        target = (
            live_sessions()
            .filter(table=table)
            .exclude(pk=source.pk)
            .order_by("opened_at", "id")
            .first()
        )
    if target is None or target.pk == source.pk or target.status != S.OPEN:
        raise Conflict(str(NOTHING_TO_MERGE), code="table.nothing_to_merge")
    return target


@operation(
    "table.session.merge",
    kind="command",
    permission="table.transfer_session",
    input=SessionMergeIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Join a table's check into the open check of another table (or the other check of a split "
        "table): its lines move to that check in Sales, and its table frees if nothing else sits there. Ask first.",
        "risk": "high",
    },
)
def merge_session(ctx: OperationContext, data: SessionMergeIn) -> dict:
    source = _open_session(data, lock=False)
    target = _merge_target(data, source)
    # Both checks locked at once, always in the same order (two crossed merges never deadlock), and
    # checked again under the lock: the first merge wins and the other finds nothing to merge.
    locked = {
        row.pk: row
        for row in TableSession.objects.select_for_update(of=("self",))
        .select_related("table", "table__zone")
        .filter(pk__in=[source.pk, target.pk])
        .order_by("pk")
    }
    source, target = locked[source.pk], locked[target.pk]
    if source.status != S.OPEN:
        raise Conflict(str(SESSION_NOT_ACTIVE), code="table.session_not_active")
    if target.status != S.OPEN:
        raise Conflict(str(NOTHING_TO_MERGE), code="table.nothing_to_merge")
    now = timezone.now()
    order_id, kept = source.order_id, target.order_id
    # The absorbed check keeps its check of Sales when both had one (Sales voids it, and what it already
    # charged still counts as its own); when the one that stays had none, it hands it over.
    source.status, source.closed_at, source.merged_into = S.MERGED, now, target
    if kept is None:
        source.order_id = None
    _stamp(source, ctx)
    source.save()
    _release(source, SessionMove.Release.MERGED, now)
    if order_id is not None and kept is not None:
        call_app(
            ctx,
            "sale.order.merge",
            {"from_order_id": str(order_id), "to_order_id": str(kept)},
        )
    elif order_id is not None:
        target.order_id = order_id
        _stamp(target, ctx)
        target.save()
        retitle(ctx, order_id, target.table)
    _event(
        ctx,
        events.SESSION_MERGED,
        source,
        into_id=str(target.pk),
        into_table_id=str(target.table_id),
        order_id=str(target.order_id) if target.order_id else None,
    )
    return session_out(target)


@operation(
    "table.session.split",
    kind="command",
    permission="table.change_session",
    input=SessionSplitIn,
    output=SplitOut,
    expose_api=True,
    ai={
        "description": "Split a table's check in two so each part pays separately: a second check opens at the same "
        "table and the lines named move to it in Sales (none = a blank check).",
        "risk": "normal",
        # Done at the table with the party, never by an automation (TABLE-F17).
        "in_person": True,
    },
)
def split_session(ctx: OperationContext, data: SessionSplitIn) -> dict:
    session = _open_session(data)
    now = timezone.now()
    # Splitting seats nobody new: the new check stays at the check's own table, blocked or inactive too.
    table = find_table(session.table_id, None, lock=True)
    label = title(ctx, table)
    if order_is_open(session.order_id):
        split = call_app(
            ctx,
            "sale.order.split",
            {
                "order_id": str(session.order_id),
                "line_ids": [str(line) for line in data.line_ids],
                "label": label,
            },
        )
        new_order_id = split.new_order.id
    else:
        new_order_id = call_app(ctx, "sale.order.open", {"label": label}).id
    new = TableSession(
        table=table,
        order_id=new_order_id,
        guests_count=data.guests_count,
        notes=data.notes,
        waiter_id=session.waiter_id,
        waiter_name=session.waiter_name,
        opened_at=now,
        split_from=session,
    )
    _stamp(new, ctx, created=True)
    new.save()
    _seat_at(new, table, SessionMove.Reason.SPLIT, now)
    _event(
        ctx,
        events.SESSION_SPLIT,
        new,
        from_id=str(session.pk),
        order_id=str(new_order_id),
    )
    return {"session": session_out(session), "new_session": session_out(new)}


@operation(
    "table.session.set_guests",
    kind="command",
    permission="table.change_session",
    input=SessionGuestsIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Correct how many guests sit at a table's open check (e.g. one more joined).",
        "risk": "normal",
    },
)
def set_guests(ctx: OperationContext, data: SessionGuestsIn) -> dict:
    session = _open_session(data)
    session.guests_count = data.guests_count
    _stamp(session, ctx)
    session.save()
    _event(ctx, events.SESSION_UPDATED, session)
    return session_out(session)


@operation(
    "table.session.park",
    kind="command",
    permission="table.change_session",
    input=SessionRefIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Take the table away from a check without closing it (park it): the table frees, the check "
        "stays open in Sales with its guests, waiter and time, and can be seated again later.",
        "risk": "normal",
    },
)
def park_session(ctx: OperationContext, data: SessionRefIn) -> dict:
    session = _open_session(data)
    table_id = session.table_id
    now = timezone.now()
    _release(session, SessionMove.Release.PARKED, now)
    session.status, session.table = S.PARKED, None
    _stamp(session, ctx)
    session.save()
    record_event(
        ctx, events.SESSION_PARKED, {"id": str(session.pk), "table_id": str(table_id)}
    )
    return session_out(session)


@operation(
    "table.session.restore",
    kind="command",
    permission="table.change_session",
    input=SessionRestoreIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Seat a parked check at a free table again, with its guests, waiter and opening time; its "
        "check of Sales takes the table's title.",
        "risk": "normal",
        # Seating the party again, by the waiter, never by an automation (TABLE-F24).
        "in_person": True,
    },
)
def restore_session(ctx: OperationContext, data: SessionRestoreIn) -> dict:
    # A parked check whose check of Sales already ended is closed, not parked any more.
    session = _settled(find_session(data.id, None, lock=True))
    if session.status != S.PARKED:
        raise Conflict(str(SESSION_NOT_PARKED), code="table.session_not_parked")
    if session.order_id is not None and not order_is_open(session.order_id):
        raise Conflict(str(ORDER_NOT_OPEN), code="table.order_not_open")
    now = timezone.now()
    table = _seatable_table(data.table_id, data.table, data.zone, now)
    session.status, session.table = S.OPEN, table
    _stamp(session, ctx)
    session.save()
    _seat_at(session, table, SessionMove.Reason.RESTORED, now)
    retitle(ctx, session.order_id, table)
    _event(ctx, events.SESSION_RESTORED, session)
    return session_out(session)


@operation(
    "table.session.link_order",
    kind="command",
    permission="table.add_session",
    input=SessionLinkOrderIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Make an open check of Sales the check of a table's open check that has none yet (the till "
        "opened it apart); it takes the table's title.",
        "risk": "normal",
        # Bringing the party's check to its table, by the waiter, never by an automation (TABLE-F12).
        "in_person": True,
    },
)
def link_order(ctx: OperationContext, data: SessionLinkOrderIn) -> dict:
    session = _open_session(data)
    if session.order_id == data.order_id:
        return session_out(session)
    if session.order_id is not None and order_is_open(session.order_id):
        raise Conflict(str(BILL_MISMATCH), code="table.session_bill_mismatch")
    _bring_order(ctx, data.order_id, session.table)
    session.order_id = data.order_id
    _stamp(session, ctx)
    session.save()
    _event(ctx, events.SESSION_UPDATED, session)
    return session_out(session)


@operation(
    "table.session.delete",
    kind="command",
    permission="table.delete_session",
    input=ByIdIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a finished table check from the history (an open or parked one is refused). It is kept "
        "as deleted, with its trail through the tables. Ask first.",
        "risk": "high",
    },
)
def delete_session(ctx: OperationContext, data: ByIdIn) -> dict:
    session = _settled(find_session(data.id, None, lock=True))
    if session.status in (S.OPEN, S.PARKED):
        raise Conflict(str(SESSION_STILL_OPEN), code="table.session_still_open")
    session.is_deleted, session.deleted_at = True, timezone.now()
    _stamp(session, ctx)
    session.save()
    record_event(ctx, events.SESSION_DELETED, {"id": str(session.pk)})
    return {"id": session.pk}


@operation(
    "table.session.close_by_order",
    kind="command",
    permission=SYSTEM,
    input=ByOrderIn,
    output=ClosedOut,
    ai={
        "description": "Platform only: close the table checks of a check of Sales charged in full or voided.",
        "risk": "normal",
    },
)
def close_by_order(ctx: OperationContext, data: ByOrderIn) -> dict:
    now = timezone.now()
    sessions = list(
        TableSession.objects.select_for_update().filter(
            order_id=data.order_id, status__in=LIVE, is_deleted=False
        )
    )
    for session in sessions:
        session.status, session.closed_at = S.CLOSED, now
        session.save(update_fields=["status", "closed_at", "updated_at"])
        _release(session, SessionMove.Release.CLOSED, now)
        _event(ctx, events.SESSION_CLOSED, session, order_id=str(data.order_id))
    return {"closed": len(sessions)}


# ── Holds ────────────────────────────────────────────────────────────────────────────────────────


def _in_service(table: Table) -> bool:
    return (
        table.is_active
        and not table.is_deleted
        and (
            table.zone_id is None
            or (table.zone.is_active and not table.zone.is_deleted)
        )
    )


def _hold_event(ctx: OperationContext, name: str, hold: Hold) -> None:
    record_event(
        ctx,
        name,
        {
            "table_id": str(hold.table_id),
            "source": hold.source,
            "source_ref": hold.source_ref,
        },
    )


@operation(
    "table.hold.place",
    kind="command",
    permission="table.change_session",
    input=HoldPlaceIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Set a table aside by hand for a party («keep table 6 for Pedro from 21:00 to 23:00, 4 people»): "
        "from an hour before it shows Reserved with the name. Asking again with the same reference changes the same hold.",
        "risk": "normal",
    },
)
def place_hold(ctx: OperationContext, data: HoldPlaceIn) -> dict:
    table = find_table(data.table_id, data.table, data.zone)
    if not _in_service(table):
        raise Conflict(str(TABLE_NOT_AVAILABLE), code="table.table_not_available")
    hold = (
        Hold.objects.select_for_update()
        .filter(source=Hold.Source.MANUAL, source_ref=data.source_ref)
        .first()
    )
    if hold is None:
        hold = Hold(source=Hold.Source.MANUAL, source_ref=data.source_ref)
        _stamp(hold, ctx, created=True)
    hold.table, hold.held_from, hold.held_until = table, data.held_from, data.held_until
    hold.party_size, hold.label, hold.status = (
        data.party_size,
        data.label,
        Hold.Status.HELD,
    )
    _stamp(hold, ctx)
    hold.save()
    _hold_event(ctx, events.TABLE_HELD, hold)
    return hold_row(hold)


@operation(
    "table.hold.release",
    kind="command",
    permission="table.change_session",
    input=HoldReleaseIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Release a table set aside (by the hold's reference): its name is forgotten.",
        "risk": "normal",
    },
)
def release_hold(ctx: OperationContext, data: HoldReleaseIn) -> dict:
    hold = (
        Hold.objects.select_for_update()
        .filter(source=data.source, source_ref=data.source_ref, status=Hold.Status.HELD)
        .first()
    )
    if hold is None:
        raise NotFound(str(HOLD_NOT_FOUND), code="table.hold_not_found")
    hold.status, hold.label = Hold.Status.RELEASED, ""
    _stamp(hold, ctx)
    hold.save()
    _hold_event(ctx, events.TABLE_HOLD_RELEASED, hold)
    return hold_row(hold)


@operation(
    "table.hold.expire",
    kind="command",
    permission=SYSTEM,
    input=NoIn,
    output=ExpiredOut,
    ai={
        "description": "Platform only: mark expired the holds whose window passed, forgetting their names.",
        "risk": "normal",
    },
)
def expire_holds(ctx: OperationContext, data: NoIn) -> dict:
    over = list(
        Hold.objects.select_for_update()
        .filter(status=Hold.Status.HELD, held_until__lte=timezone.now())
        .order_by("pk")
    )
    for hold in over:
        hold.status = Hold.Status.EXPIRED
        hold.label = ""
        hold.save(update_fields=["status", "label", "updated_at"])
        # One notice per hold, saying its table (hub#2681): never one for the whole sweep.
        _hold_event(ctx, events.TABLE_HOLD_RELEASED, hold)
    return {"expired": len(over)}


def _window(day: dt.date, at: dt.time, minutes: int) -> tuple[dt.datetime, dt.datetime]:
    """A reservation's window: it starts at its wall-clock day and time in the business's zone and lasts
    its minutes of real time, in UTC (wall-clock arithmetic held a table an hour longer or shorter the
    night the clocks change). A time that happens twice is the occurrence ``at.fold`` says (a time from
    Reservations: the first); a time the clocks skip moves forward by the gap."""
    start = dt.datetime.combine(day, at, tzinfo=business_zone()).astimezone(dt.UTC)
    return start, start + dt.timedelta(minutes=minutes)


RELEASING = {"cancelled", "no_show", "deleted"}


@operation(
    "table.hold.sync_reservation",
    kind="command",
    permission=SYSTEM,
    input=ReservationStatusIn,
    output=HoldsChangedOut,
    ai={
        "description": "Platform only: a reservation confirmed holds its table; cancelled or not shown releases it.",
        "risk": "normal",
    },
)
def sync_reservation(ctx: OperationContext, data: ReservationStatusIn) -> dict:
    current = (
        Hold.objects.select_for_update()
        .filter(source=Hold.Source.RESERVATION, source_ref=data.id)
        .first()
    )
    if data.status in RELEASING:
        if current is None or current.status != Hold.Status.HELD:
            return {"changed": 0}
        current.status, current.label = Hold.Status.RELEASED, ""
        current.save()
        _hold_event(ctx, events.TABLE_HOLD_RELEASED, current)
        return {"changed": 1}
    if data.status != "confirmed" or not (data.table_id and data.date and data.time):
        return {"changed": 0}
    if current is not None and current.status == Hold.Status.CONSUMED:
        return {"changed": 0}
    table = Table.objects.select_related("zone").filter(pk=data.table_id).first()
    if table is None or not _in_service(table):
        return {"changed": 0}
    hold = current or Hold(source=Hold.Source.RESERVATION, source_ref=data.id)
    hold.table = table
    hold.held_from, hold.held_until = _window(
        data.date, data.time, data.duration_minutes or DEFAULT_RESERVATION_MINUTES
    )
    hold.party_size, hold.label, hold.customer_id = (
        data.party_size or 0,
        data.guest_name,
        data.customer_id,
    )
    hold.status = Hold.Status.HELD
    hold.save()
    _hold_event(ctx, events.TABLE_HELD, hold)
    return {"changed": 1}


@operation(
    "table.hold.move_reservation",
    kind="command",
    permission=SYSTEM,
    input=ReservationUpdatedIn,
    output=HoldsChangedOut,
    ai={
        "description": "Platform only: a reservation changed moves its hold (table, day, time, duration, guests, name); "
        "one left without a table releases it.",
        "risk": "normal",
    },
)
def move_reservation(ctx: OperationContext, data: ReservationUpdatedIn) -> dict:
    hold = (
        Hold.objects.select_for_update()
        .select_related("table")
        .filter(
            source=Hold.Source.RESERVATION, source_ref=data.id, status=Hold.Status.HELD
        )
        .first()
    )
    if hold is None:
        return {"changed": 0}
    sent = data.model_fields_set
    if "table_id" in sent and data.table_id is None:
        hold.status, hold.label = Hold.Status.RELEASED, ""
        hold.save()
        _hold_event(ctx, events.TABLE_HOLD_RELEASED, hold)
        return {"changed": 1}
    if data.table_id is not None and data.table_id != hold.table_id:
        table = Table.objects.select_related("zone").filter(pk=data.table_id).first()
        if table is None or not _in_service(table):
            return {"changed": 0}
        hold.table = table
    if sent & {"date", "time", "duration_minutes"}:
        local = timezone.localtime(hold.held_from, business_zone())
        minutes = data.duration_minutes or int(
            (hold.held_until - hold.held_from).total_seconds() // 60
        )
        hold.held_from, hold.held_until = _window(
            data.date or local.date(), data.time or local.time(), minutes
        )
    if "party_size" in sent and data.party_size is not None:
        hold.party_size = data.party_size
    if "guest_name" in sent:
        hold.label = data.guest_name
    hold.save()
    _hold_event(ctx, events.TABLE_HELD, hold)
    return {"changed": 1}


@operation(
    "table.hold.forget_customer",
    kind="command",
    permission=SYSTEM,
    input=CustomerErasedIn,
    output=HoldsChangedOut,
    ai={
        "description": "Platform only: forget the name on every hold of a customer whose data was erased.",
        "risk": "normal",
    },
)
def forget_customer(ctx: OperationContext, data: CustomerErasedIn) -> dict:
    if data.id is None:
        return {"changed": 0}
    named = list(
        Hold.objects.select_for_update()
        .filter(customer_id=data.id)
        .exclude(label="")
        .order_by("pk")
    )
    for hold in named:
        hold.label = ""
        hold.save(update_fields=["label", "updated_at"])
        # The live plan paints the hold again, now without her name (TABLE-F09).
        _hold_event(ctx, events.TABLE_HELD, hold)
    return {"changed": len(named)}


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


def _settings_row_locked() -> TableSettings:
    """The settings' one row, locked; created with the factory values the first time. Two first saves at
    once: the second one's row loses to the unique single row, and it takes the first one's, locked."""
    settings = TableSettings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return TableSettings.objects.create()
    except IntegrityError:
        return TableSettings.objects.select_for_update().get()


@operation(
    "table.settings.update",
    kind="command",
    permission="table.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change the room settings: whether seating asks for the guests, and after how many minutes an "
        "open check turns amber and red. Only what is sent changes.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    changes = {
        field: value for field, value in data.model_dump(exclude_none=True).items()
    }
    settings = _settings_row_locked() if changes else current_settings()
    for field, value in changes.items():
        setattr(settings, field, value)
    if settings.timer_critical_minutes < settings.timer_warning_minutes:
        raise InvalidPayload(
            str(RED_BEFORE_AMBER),
            fields={"timer_critical_minutes": str(RED_BEFORE_AMBER)},
        )
    if changes:
        settings.updated_by = actor_label(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)
