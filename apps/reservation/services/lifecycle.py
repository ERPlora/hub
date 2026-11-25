"""The states of a reservation (RESERVATION-F07, F09 to F13, F20): confirmed, seated, completed, cancelled, not shown
and deleted, and the pending ones nobody confirmed released.
"""

import datetime as dt

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.reservation import engine, events
from apps.reservation.models import Reservation
from apps.reservation.queries.clock import business_now, starts_at
from apps.reservation.queries.gate import in_service
from apps.reservation.schemas.fields import DeletedOut, NoIn
from apps.reservation.schemas.reservations import CancelIn, ReleasedOut, ReservationOut, ReservationRefIn
from apps.reservation.services.gate import lock_book, refuse
from apps.reservation.services.other_apps import status_changed, sync_hold
from apps.reservation.services.reservations import _loaded, _named
from apps.reservation.services.seating import seat_at_table
from apps.reservation.services.writes import S, _stamp
from apps.table.models import Table
from apps.table.queries import floor

#: The reason a reservation released unconfirmed keeps (the screen translates it).
UNCONFIRMED = "unconfirmed"

#: The steps a reservation may take: target → the statuses it may come from.
STEPS = {
    S.CONFIRMED: (S.PENDING,),
    S.SEATED: (S.PENDING, S.CONFIRMED),
    S.COMPLETED: (S.SEATED,),
    S.CANCELLED: (S.PENDING, S.CONFIRMED),
    S.NO_SHOW: (S.PENDING, S.CONFIRMED),
}
TERMINAL = (S.COMPLETED, S.CANCELLED, S.NO_SHOW)
STATUS_FINAL = _("This reservation is %(status)s: its status can no longer change.")
COMPLETE_BEFORE_SEAT = _(
    "This reservation is %(status)s: it cannot be completed before it is seated."
)
STEP_REFUSED = _("This reservation is %(status)s: it cannot be %(target)s.")
#: The verbs of each step, as the refusal says them («it cannot be confirmed»).
TARGET_WORDS = {
    S.CONFIRMED: pgettext_lazy("reservation step", "confirmed"),
    S.SEATED: pgettext_lazy("reservation step", "seated"),
    S.COMPLETED: pgettext_lazy("reservation step", "completed"),
    S.CANCELLED: pgettext_lazy("reservation step", "cancelled"),
    S.NO_SHOW: pgettext_lazy("reservation step", "marked a no-show"),
}


def step(ctx: OperationContext, reservation: Reservation, target: str) -> str:
    """Moves ``reservation`` to ``target`` if it may (stamping the time), else the readable refusal."""
    current = reservation.status
    if current not in STEPS[target]:
        label = str(Reservation.Status(current).label).lower()
        if current in TERMINAL:
            message = str(STATUS_FINAL) % {"status": label}
        elif target == S.COMPLETED:
            message = str(COMPLETE_BEFORE_SEAT) % {"status": label}
        else:
            message = str(STEP_REFUSED) % {
                "status": label,
                "target": TARGET_WORDS[target],
            }
        raise Conflict(message, code="reservation.illegal_transition")
    now = timezone.now()
    reservation.status = target
    stamp_field = {
        S.CONFIRMED: "confirmed_at",
        S.SEATED: "seated_at",
        S.COMPLETED: "completed_at",
        S.CANCELLED: "cancelled_at",
        S.NO_SHOW: "no_show_at",
    }[target]
    setattr(reservation, stamp_field, now)
    _stamp(reservation, ctx)
    return current


def held_table(reservation: Reservation) -> None:
    """A reservation confirmed with a table holds it: a table out of service (blocked, out of use, deleted,
    or in a zone out of use) would hold nothing (TABLE-F25), so it is refused."""
    if reservation.table_id is None:
        return
    table = Table.objects.select_related("zone").get(pk=reservation.table_id)
    if not in_service(table):
        raise refuse(engine.Refusal("table_unavailable", {"table": floor.table_label(table)}))


@operation(
    "reservation.reservation.confirm",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "confirm Luis's booking for Saturday",
                "Marta called to say she is coming: confirm her reservation",
            ),
            "es": (
                "confirma la reserva de Luis del sábado",
                "Marta ha llamado para decir que viene: confírmale la reserva",
            ),
        },
        "description": "Confirms a pending reservation (by id, or by its guest and day). With a table, the floor plan "
        "shows it Reserved from an hour before.",
        "risk": "normal",
    },
)
def confirm_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(ctx, data)
    held_table(reservation)
    previous = step(ctx, reservation, S.CONFIRMED)
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.CONFIRMED)
    return _loaded(ctx, reservation)


@operation(
    "reservation.reservation.seat",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Luis's booking has arrived, seat them",
                "seat Marta's party at their reserved table",
            ),
            "es": (
                "ha llegado la reserva de Luis, pásalos a su mesa",
                "ya están aquí los de la reserva de Marta, dales su mesa",
            ),
        },
        "description": "Seats a pending or confirmed reservation when the party arrives (by id, or by its guest and "
        "day). If its table is free, the party is seated there in Tables with its guests and customer: the table's "
        "check opens in Sales. A table that is taken is refused (free it or move the reservation first), unless "
        "this party was already seated at it from the floor plan: then only the reservation is marked.",
        "risk": "normal",
        # Done at the door by whoever receives the party, never by an automation (FLOW-F12).
        "in_person": True,
    },
)
def seat_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(ctx, data)
    previous = step(ctx, reservation, S.SEATED)
    if reservation.table_id is not None:
        reservation.table_session_id = seat_at_table(ctx, reservation)
    reservation.save()
    status_changed(ctx, reservation, previous)
    return _loaded(ctx, reservation)


@operation(
    "reservation.reservation.complete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Luis's party has left, complete the booking",
                "mark Marta's reservation as completed",
            ),
            "es": (
                "los de la reserva de Luis ya se han ido, ciérrala",
                "da por terminada la reserva de Marta",
            ),
        },
        "description": "Completes a seated reservation when the party leaves (by id, or by its guest and day).",
        "risk": "normal",
    },
)
def complete_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(ctx, data)
    previous = step(ctx, reservation, S.COMPLETED)
    reservation.save()
    status_changed(ctx, reservation, previous)
    return _loaded(ctx, reservation)


@operation(
    "reservation.reservation.cancel",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=CancelIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "cancel Luis's booking for Saturday",
                "Marta can't make it, call off her reservation",
            ),
            "es": (
                "anula la reserva de Luis del sábado",
                "Marta no puede venir, cancélale la reserva",
            ),
        },
        "description": "Cancels a pending or confirmed reservation (by id, or by its guest and day), with an optional "
        "reason: its place and its table are freed.",
        "risk": "high",
    },
)
def cancel_reservation(ctx: OperationContext, data: CancelIn) -> dict:
    reservation = _named(ctx, data)
    previous = step(ctx, reservation, S.CANCELLED)
    reservation.cancellation_reason = data.reason
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.CANCELLED)
    return _loaded(ctx, reservation)


@operation(
    "reservation.reservation.no_show",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=ReservationRefIn,
    output=ReservationOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Luis never turned up for his booking",
                "mark Marta's reservation as a no-show",
            ),
            "es": (
                "Luis no ha aparecido a su reserva",
                "marca la reserva de Marta como no presentada",
            ),
        },
        "description": "Marks a pending or confirmed reservation as a no-show (by id, or by its guest and day): its "
        "place and its table are freed.",
        "risk": "high",
    },
)
def no_show_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(ctx, data)
    previous = step(ctx, reservation, S.NO_SHOW)
    reservation.save()
    status_changed(ctx, reservation, previous)
    sync_hold(ctx, reservation, S.NO_SHOW)
    return _loaded(ctx, reservation)


@operation(
    "reservation.reservation.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.delete_reservation",
    input=ReservationRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete Luis's reservation for good",
                "erase Marta's duplicate booking",
            ),
            "es": (
                "elimina del todo la reserva de Luis",
                "borra la reserva repetida de Marta",
            ),
        },
        "description": "Deletes a reservation from the book for good (by id, or by its guest and day); its table is "
        "freed. When the person asks to delete or erase it; to call it off and keep it with its reason is to cancel it.",
        "risk": "high",
    },
)
def delete_reservation(ctx: OperationContext, data: ReservationRefIn) -> dict:
    reservation = _named(ctx, data)
    reservation.is_deleted = True
    reservation.deleted_at = timezone.now()
    _stamp(reservation, ctx)
    reservation.save()
    record_event(ctx, events.RESERVATION_DELETED, {"id": str(reservation.pk)})
    status_changed(ctx, reservation, reservation.status, status="deleted")
    sync_hold(ctx, reservation, "deleted")
    return {"id": reservation.pk}


@operation(
    "reservation.reservation.release_unconfirmed",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_reservation",
    input=NoIn,
    output=ReleasedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "let go of the bookings nobody confirmed",
                "release the unconfirmed reservations whose time has passed",
            ),
            "es": (
                "suelta las reservas que nadie ha confirmado",
                "suelta las reservas de hoy que siguen pendientes y ya pasó su hora",
            ),
        },
        "description": "Releases the pending reservations nobody confirmed whose time passed more than the book's "
        "window (15 minutes): they are cancelled as «unconfirmed» and free their place. Runs every quarter of an hour; "
        "safe to run by hand.",
        "risk": "normal",
    },
)
def release_unconfirmed(ctx: OperationContext, data: NoIn) -> dict:
    window = dt.timedelta(minutes=lock_book().no_show_window_minutes)
    now = timezone.now()
    stale = [
        row
        for row in Reservation.objects.select_for_update()
        .filter(is_deleted=False, status=S.PENDING, date__lte=business_now().date())
        .order_by("date", "time", "id")
        if starts_at(row.date, row.time) + window < now
    ]
    stamp = timezone.now()
    for row in stale:
        row.status, row.cancelled_at, row.cancellation_reason = (
            S.CANCELLED,
            stamp,
            UNCONFIRMED,
        )
        _stamp(row, ctx)
        row.save()
    if stale:
        record_event(
            ctx, events.RESERVATION_UNCONFIRMED_RELEASED, {"count": len(stale)}
        )
    return {"released": len(stale)}
