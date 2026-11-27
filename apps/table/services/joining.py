"""Joining the checks of two tables into one and splitting a table's check in two (TABLE-F16, F17)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation

from apps.table import events
from apps.table.models import SessionMove, TableSession
from apps.table.queries.lookups import find_session, find_table
from apps.table.queries.sessions import order_is_open, session_out
from apps.table.queries.floor import live_sessions
from apps.table.schemas.sessions import SessionMergeIn, SessionOut, SessionSplitIn, SplitOut
from apps.table.services.writes import (
    S,
    SESSION_NOT_ACTIVE,
    _event,
    _open_session,
    _release,
    _seat_at,
    _settled,
    _stamp,
    call_app,
    retitle,
    settle,
    title,
)

NOTHING_TO_MERGE = _("That table has no other open check to merge with.")


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.transfer_session",
    input=SessionMergeIn,
    output=SessionOut,
    expose_api=True,
    ai={
        "description": "Join a table's check into the open check of another table (or the other check of a split "
        "table): its lines move to that check in Sales, and its table frees if nothing else sits there. Tables go by "
        "their number (and zone); the two checks of a split table, by the ids table.table.get lists.",
        "risk": "high",
        "asks": {
            "en": (
                "join tables 4 and 5 into one check",
                "merge table 2's check into table 3's",
                "tables 7 and 8 are paying together, combine them",
            ),
            "es": (
                "junta la mesa 4 con la mesa 5, que pagan juntos",
                "une las mesas 2 y 3 en una sola",
                "fusiona la cuenta de la mesa 7 con la de la 8",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=SessionSplitIn,
    output=SplitOut,
    expose_api=True,
    ai={
        "description": "Split a table's check in two so each part pays separately: a second check opens at the same "
        "table and the lines named move to it in Sales (none = a blank check). Use this, not sale.order.split nor "
        "sale.order.open, for a check seated at a table (a second check for someone who pays apart too): only this "
        "one keeps both checks at the table. The table goes by its number (and "
        "zone); at a table with two checks already, the check's id comes from table.table.get, and the lines to move "
        "from sale.order.get.",
        "risk": "normal",
        # Done at the table with the party, never by an automation (TABLE-F17).
        "in_person": True,
        "asks": {
            "en": (
                "split table 4's check, they're paying separately",
                "open a separate check at table 2 for one of them",
                "table 6 wants two checks, one of them pays on their own",
            ),
            "es": (
                "divide la cuenta de la mesa 4, pagan por separado",
                "sepárame la cuenta de la 2, uno paga aparte",
                "abre otra cuenta en la mesa 6 para uno que paga lo suyo",
            ),
        },
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
