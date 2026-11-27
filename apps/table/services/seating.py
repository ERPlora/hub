"""Seating a party, closing its check by hand and moving it to another table (TABLE-F10, F15, F21, F28, F32)."""

import logging
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import atomic, operation

from apps.customer.queries.reads import find_customer
from apps.sale.models import Order
from apps.table import events
from apps.table.models import SessionMove, TableSession
from apps.table.queries.sessions import session_out
from apps.table.schemas.sessions import SessionCloseIn, SessionOpenIn, SessionOut, SessionTransferIn
from apps.table.services.writes import (
    BILL_MISMATCH,
    S,
    _bring_order,
    _event,
    _open_session,
    _parked_holding,
    _release,
    _reseat,
    _seat_at,
    _seatable_table,
    _seating_holds,
    _stamp,
    actor_id,
    actor_label,
    call_app,
    retitle,
    title,
)

# The writes of the table app log under the package's name, whichever of its modules writes the line.
logger = logging.getLogger("apps.table.services")

BILL_OPEN = _(
    "This table's bill is still open in Sales: charge it, move it to another table or delete it from the till."
)


def _put_customer(ctx: OperationContext, order_id: UUID, customer_id: UUID | None, said: str | None) -> None:
    """Puts the customer on the table's check (Customers' link). If Customers refuses (no such card, several
    match, not allowed), the table is seated all the same and the check stays without one (TABLE-F32): the
    reply says so with its empty customer."""
    try:
        with atomic():
            customer = find_customer(ctx, customer_id, said)
            call_app(ctx, "customer.order.link", {"order_id": str(order_id), "customer_id": str(customer.pk)})
    except OperationError as refusal:
        logger.info("table: seated without the customer (%s)", refusal.code)


@operation(
    "table.session.open",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.add_session",
    input=SessionOpenIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Seat a party at a free or reserved table («seat 3 at table 4»): its check opens in Sales titled "
        "with the table. Use this, not sale.order.open, whenever people sit at a table: that one opens a check no "
        "table holds. Without guests, the reservation's or the table's seats. Optionally bring an open check of Sales "
        "to the table (its order_id, from sale.order.list), and put a customer (by name or phone) on the check. A "
        "parked check of Sales brought here sits again as it was, with its guests, waiter and opening time.",
        "risk": "normal",
        # Done by the waiter with the party in front, never by an automation (TABLE-F10).
        "in_person": True,
        "asks": {
            "en": (
                "seat 3 at table 4",
                "a party of two just sat down at table 7",
                "put Ana's check on table 4",
            ),
            "es": (
                "sienta a tres en la mesa 4",
                "han llegado dos para la mesa 7",
                "abre la mesa 5 para cuatro",
            ),
        },
    },
)
def open_session(ctx: OperationContext, data: SessionOpenIn) -> dict:
    if data.order_id is not None and (parked := _parked_holding(data.order_id)) is not None:
        return _reseat(ctx, parked, data)
    now = timezone.now()
    table = _seatable_table(data.table_id, data.table, data.zone, now)
    hold = _seating_holds(table, now, data.reservation_id).filter(party_size__gt=0).order_by("held_from", "id").first()
    guests = data.guests_count or (hold.party_size if hold else table.capacity)
    # Only a new check takes the reservation's customer: linking one to a brought check would replace its own.
    reserved_for = hold.customer_id if hold and data.order_id is None and not data.customer else None
    customer_id = data.customer_id or reserved_for
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
    if customer_id or data.customer:
        _put_customer(ctx, order_id, customer_id, data.customer)
    _event(
        ctx, events.SESSION_OPENED, session, order_id=str(order_id), guests_count=guests
    )
    return session_out(session)


@operation(
    "table.session.close",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=SessionCloseIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Close a table's check by hand and free the table if nothing else sits there. A check with "
        "something ordered still open in Sales is refused (charge it, move it or delete it first); an empty one is "
        "voided in Sales.",
        "risk": "high",
        "asks": {
            "en": (
                "close table 4, they've left",
                "free table 2, they didn't order anything",
                "table 9 is done, close it",
            ),
            "es": (
                "cierra la mesa 4, ya se han ido",
                "libera la mesa 2, que no pidieron nada",
                "la 9 ya ha terminado, ciérrala",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.transfer_session",
    input=SessionTransferIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Move a table's check to a free or reserved table («move table 4 to 6»): same check of Sales "
        "(retitled), guests, waiter and notes; the old table frees if nothing else sits there. Use this, not "
        "sale.order.set_label: retitling a check moves nobody. Both tables go by their number (and zone); at a table "
        "with two checks, the check's id comes from table.table.get.",
        "risk": "high",
        "asks": {
            "en": (
                "move table 4 to 6",
                "they want to sit outside, take their check to table 12",
                "transfer table 3's check to table 10",
            ),
            "es": (
                "pasa la mesa 4 a la 6",
                "los de la 3 se mudan a la mesa 10",
                "se quieren ir fuera, llévate su cuenta a la mesa 12",
            ),
        },
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
