"""Setting tables aside: by hand, for the reservations of Reservations, and forgetting the name of an erased customer
(TABLE-F25, F26, F27, F29, F30, F31).
"""

import datetime as dt

from django.utils import timezone
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.table import events
from apps.table.models import Hold, Table
from apps.table.queries.holds import HOLD_NOT_FOUND, hold_row
from apps.table.queries.lookups import find_table
from apps.table.schemas.fields import NoIn
from apps.table.schemas.holds import (
    CustomerErasedIn,
    ExpiredOut,
    HoldOut,
    HoldPlaceIn,
    HoldReleaseIn,
    HoldsChangedOut,
    ReservationStatusIn,
    ReservationUpdatedIn,
)
from apps.table.services.writes import SYSTEM, TABLE_NOT_AVAILABLE, _stamp
from base.business import business_zone

#: How long a reservation holds its table when it does not say.
DEFAULT_RESERVATION_MINUTES = 120


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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=HoldPlaceIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Set a table aside by hand for a party («keep table 6 for Pedro from 21:00 to 23:00, 4 people»): "
        "from an hour before it shows Reserved with the name. Asking again with the same reference changes the same hold.",
        "risk": "normal",
        "asks": {
            "en": (
                "keep table 6 for Pedro from 9 to 11pm, 4 people",
                "save table 3 for the Garcias tonight",
            ),
            "es": (
                "guarda la 6 para Pedro de 21:00 a 23:00, 4 personas",
                "apártame la mesa 3 para los García esta noche",
            ),
        },
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
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.change_session",
    input=HoldReleaseIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Release a table set aside (by the hold's reference): its name is forgotten.",
        "risk": "normal",
        "asks": {
            "en": (
                "release the table we kept for Pedro",
                "drop the hold on table 6",
            ),
            "es": (
                "suelta la mesa que guardamos para Pedro",
                "ya no hace falta apartar la mesa 6, libérala",
            ),
        },
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
        # One notice per hold, saying its table: never one for the whole sweep.
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
