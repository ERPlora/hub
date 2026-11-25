"""The steps every write of the table app shares: who acts, Sales and Customers reached by their operations in the same
transaction, closing the checks Sales already ended, finding the open check, seating a check at a table and ending its
stretch there.
"""

import datetime as dt
from uuid import UUID

from django.utils import timezone, translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict
from live.operations import UnknownOperation, get
from live.outbox import record_event

from apps.sale.models import Order
from apps.table.models import ACTOR_MAX_LENGTH, Hold, SessionMove, Table, TableSession
from apps.table.queries.lookups import find_session, find_table
from apps.table.queries.sessions import check_label, order_is_open
from apps.table.queries.tables import seatable
from apps.table.queries.floor import ended_orders, reserving_holds
from base.queries.people import actor_name

S = TableSession.Status
#: The checks still alive: seated (open) or parked; Sales ending their check ends them.
LIVE = [S.OPEN, S.PARKED]

#: The platform's own writes (reactions, the sweep): the system has «*»; no role is given this one.
SYSTEM = "table.system"

TABLE_NOT_AVAILABLE = _(
    "That table cannot be seated right now: it is taken, out of service or no longer in use."
)
SESSION_NOT_ACTIVE = _(
    "That check is not open: it does not exist in this business, or it has already been closed, "
    "transferred, merged or parked."
)
BILL_MISMATCH = _("This table's bill has changed. Reload the list and try again.")
ORDER_NOT_OPEN = _("That check is no longer open in Sales.")
ORDER_ELSEWHERE = _("That check is already at table %(table)s.")
SALE_UNAVAILABLE = _(
    "Sales is not available in this business: the table's check cannot be opened or changed."
)


def actor_label(ctx: OperationContext) -> str:
    """Who acts, as a colleague reads them (never by their address); the system's own label."""
    return actor_name(ctx.actor)[:ACTOR_MAX_LENGTH]


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


def settle(sessions) -> None:
    """Closes the open and parked checks of ``sessions`` whose check of Sales already ended (charged in
    full or voided), at the hour Sales closed it: what the reads already show. A parked one has no
    stretch at a table left to end; it stays without a table."""
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
