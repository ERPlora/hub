"""The rest of a seated check's life: its guests, parking it and seating it again, bringing it a check of Sales,
deleting it from the history and closing it when Sales ends its check (TABLE-F12, F13, F14, F18, F20, F23, F24).
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.table import events
from apps.table.models import SessionMove, TableSession
from apps.table.queries.lookups import find_session
from apps.table.queries.sessions import order_is_open, session_out
from apps.table.schemas.fields import DeletedOut
from apps.table.schemas.sessions import (
    ByIdIn,
    ByOrderIn,
    ClosedOut,
    SessionGuestsIn,
    SessionLinkOrderIn,
    SessionOut,
    SessionRefIn,
    SessionRestoreIn,
)
from apps.table.services.writes import (
    BILL_MISMATCH,
    LIVE,
    ORDER_NOT_OPEN,
    S,
    SYSTEM,
    _bring_order,
    _event,
    _open_session,
    _release,
    _seat_at,
    _seatable_table,
    _settled,
    _stamp,
    retitle,
)

SESSION_NOT_PARKED = _(
    "That check is not parked: it does not exist in this business, or it is already seated at a table."
)
SESSION_STILL_OPEN = _("That check is still open: close it before deleting it.")


@operation(
    "table.session.set_guests",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=SessionGuestsIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Correct how many guests sit at a table's open check (e.g. one more joined). The table goes by "
        "its number (and zone); at a table with two checks, the check's id comes from table.table.get.",
        "risk": "normal",
        "asks": {
            "en": (
                "one more joined table 4, make it five",
                "table 3 is actually six people",
                "change the guests at table 6 to two",
            ),
            "es": (
                "en la mesa 4 ahora son cinco",
                "se ha sumado uno más a la mesa 3",
                "corrige los comensales de la mesa 6 a dos",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=SessionRefIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Take the table away from a check without closing it (park it): the table frees, the check "
        "stays open in Sales with its guests, waiter and time, and can be seated again later.",
        "risk": "normal",
        "asks": {
            "en": (
                "park table 4's check, they moved to the bar",
                "free table 6 but keep their check open",
                "take table 2 off its check, they'll come back later",
            ),
            "es": (
                "aparca la cuenta de la mesa 4, se han ido a la barra",
                "libera la mesa 6 pero deja su cuenta abierta",
                "quita la mesa a la cuenta de la 2, luego vuelven",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=SessionRestoreIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Seat a parked check at a free table again, with its guests, waiter and opening time; its "
        "check of Sales takes the table's title. The parked check goes by its id: find it with "
        "table.session.list(status=parked), never ask the person for it.",
        "risk": "normal",
        # Seating the party again, by the waiter, never by an automation (TABLE-F24).
        "in_person": True,
        "asks": {
            "en": (
                "seat the parked check at table 9",
                "bring the check we parked back to table 2",
                "they're back, give the parked check table 5",
            ),
            "es": (
                "vuelve a sentar la cuenta aparcada en la mesa 9",
                "la cuenta aparcada vuelve a la mesa 2",
                "ya han vuelto, siéntame la cuenta aparcada en la 5",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.add_session",
    input=SessionLinkOrderIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Link an open check of Sales (opened apart, at the till or the bar) to a table's open check "
        "that has none yet; it takes the table's title. Find the check of Sales by its title with "
        "sale.order.list(search=...) and, at a table with two checks, the table's check with table.table.get; never "
        "ask the person for an id. A party at a free table with a check of the till is seated with table.session.open.",
        "risk": "normal",
        # Bringing the party's check to its table, by the waiter, never by an automation (TABLE-F12).
        "in_person": True,
        "asks": {
            "en": (
                "table 4 has no till check yet, give it the bar one",
                "hook the open till check onto table 6",
            ),
            "es": (
                "vincula la cuenta abierta de la barra con la mesa 4",
                "engancha la cuenta abierta del TPV a la mesa 6",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.delete_session",
    input=ByIdIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "description": "Delete a finished table check from the history (an open or parked one is refused). It is kept "
        "as deleted, with its trail through the tables. It goes by its id: find the closed check the person names (its "
        "table, its time) with table.session.list(status=closed), never ask them for it.",
        "risk": "high",
        "asks": {
            "en": (
                "delete table 4's closed check from the history",
                "remove that finished check of table 2",
            ),
            "es": (
                "borra del historial la cuenta cerrada de la mesa 4",
                "quita del historial la cuenta ya cobrada de la mesa 2",
            ),
        },
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
