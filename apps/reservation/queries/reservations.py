"""The reservations: the list with its filters, and one by id or as a person says it."""

import datetime as dt
from uuid import UUID

from django.db.models import CharField, F, Func, QuerySet, Value
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.reservation.models import Reservation, WaitlistEntry
from apps.reservation.queries.business import business_now, wall_clock, window_of
from apps.reservation.queries.gate import HOLDING
from apps.reservation.queries.naming import _named, _said_day, _said_time, _who
from apps.reservation.queries.reads import MAX_CANDIDATES, _guest_matches, _page, _phone_matches, _when
from apps.reservation.schemas.reservations import (
    ReservationDetailOut,
    ReservationListIn,
    ReservationPage,
    ReservationRefIn,
)
from apps.schedule.queries.outputs import day_label
from apps.table.queries import floor
from base.ordering import list_order_for
from base.text_search import contains_text

#: What a guest's name alone names, when she has any of them.
OPEN = HOLDING

RESERVATION_NOT_FOUND = _("That reservation does not exist in this business.")
RESERVATION_AMBIGUOUS = _(
    "“%(said)s” has several reservations: %(matches)s. Say which day."
)


def reservations() -> QuerySet[Reservation]:
    """The live reservations (never the deleted ones), with their table and its zone."""
    return Reservation.objects.filter(is_deleted=False).select_related(
        "table__zone", "waitlist_entry"
    )


def _end(reservation: Reservation) -> dt.time:
    """When the stay ends on the wall clock: the night the clocks change, 90 minutes from 01:37 end at
    02:07 (the second one) in October and 90 from 01:30 at 04:00 in March."""
    window = window_of(reservation.date, reservation.time, reservation.duration_minutes)
    return wall_clock(window.end).time()


def reservation_out(ctx: OperationContext, reservation: Reservation) -> dict:
    """A ``ReservationOut``, its day and hour also ready to say in ``ctx``'s language (a reservation keeps the
    business's wall clock: no zone moves them)."""
    table = reservation.table
    try:
        entry_id = reservation.waitlist_entry.pk
    except WaitlistEntry.DoesNotExist:
        entry_id = None
    return {
        "id": reservation.pk,
        "customer_id": reservation.customer_id,
        "guest_name": reservation.guest_name,
        "guest_phone": reservation.guest_phone,
        "guest_email": reservation.guest_email,
        "date": reservation.date,
        "time": reservation.time,
        "end_time": _end(reservation),
        "date_label": day_label(reservation.date, ctx.language),
        "time_label": f"{reservation.time:%H:%M}",
        "duration_minutes": reservation.duration_minutes,
        "party_size": reservation.party_size,
        "table_id": reservation.table_id,
        "table_label": floor.table_label(table) if table is not None else "",
        "table_capacity": table.capacity if table is not None else None,
        "status": reservation.status,
        "source": reservation.source,
        "notes": reservation.notes,
        "internal_notes": reservation.internal_notes,
        "cancellation_reason": reservation.cancellation_reason,
        "confirmed_at": reservation.confirmed_at,
        "seated_at": reservation.seated_at,
        "completed_at": reservation.completed_at,
        "cancelled_at": reservation.cancelled_at,
        "no_show_at": reservation.no_show_at,
        "table_session_id": reservation.table_session_id,
        "waitlist_entry_id": entry_id,
        "created_at": reservation.created_at,
        "updated_at": reservation.updated_at,
    }


def reservation_label(ctx: OperationContext, reservation: Reservation) -> str:
    """As the book's dialogs say a reservation before a step: its guest, its day and its time."""
    return _named(_who(ctx, reservation), _said_day(reservation.date, ctx.language), _said_time(reservation.time, ctx.language))


def _hhmm(field: str) -> Func:
    """A time column as ``HH:MM`` text, to filter it by part of what the screen shows («21»)."""
    return Func(F(field), Value("HH24:MI"), function="to_char", output_field=CharField())


def find_reservation(
    ctx: OperationContext,
    reservation_id: UUID | None,
    guest: str | None,
    day: dt.date | None,
    *,
    lock: bool = False,
) -> Reservation:
    """A live reservation by id or, as a person says it, by its guest's name or phone (``_guest_matches``) and its
    day (the coming ones when no day is said; among several, the open ones)."""
    rows = reservations()
    if reservation_id is None:
        named = rows.filter(_guest_matches(ctx, guest or ""))
        named = (
            named.filter(date=day)
            if day
            else named.filter(date__gte=business_now().date())
        )
        candidates = list(named.order_by("date", "time", "id")[: MAX_CANDIDATES * 4])
        open_ones = [item for item in candidates if item.status in OPEN]
        candidates = open_ones or candidates
        if len(candidates) > 1:
            matches = ", ".join(
                f"{item.guest_name} · {_when(item.date, item.time)}"
                for item in candidates[:MAX_CANDIDATES]
            )
            raise Conflict(
                str(RESERVATION_AMBIGUOUS) % {"said": guest, "matches": matches},
                code="reservation.reservation_ambiguous",
            )
        reservation_id = candidates[0].pk if candidates else None
    if reservation_id is not None and lock:
        rows = rows.select_for_update(of=("self",))
    found = (
        rows.filter(pk=reservation_id).first() if reservation_id is not None else None
    )
    if found is None:
        raise NotFound(
            str(RESERVATION_NOT_FOUND), code="reservation.reservation_not_found"
        )
    return found


#: The list's filters that narrow by one column as they come: the input's field → its lookup.
RESERVATION_FILTERS = {
    "date_from": "date__gte",
    "date_to": "date__lte",
    "status": "status",
    "table_id": "table_id",
    "customer_id": "customer_id",
    "party_size_from": "party_size__gte",
    "party_size_to": "party_size__lte",
}
RESERVATION_SORTS = {
    "starts_at": ("date", "time"),
    "time": ("time", "date"),
    "guest_name": ("guest_name",),
    "party_size": ("party_size",),
    "table": ("table__number",),
    "status": ("status",),
    "created_at": ("created_at",),
}


@operation(
    "reservation.reservation.list",
    kind="query",
    permission="reservation.view_reservation",
    input=ReservationListIn,
    output=ReservationPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what bookings do we have tonight?",
                "show me the reservations for the weekend",
                "any pending bookings for Saturday?",
            ),
            "es": (
                "¿qué reservas tenemos esta noche?",
                "enséñame las reservas del fin de semana",
                "¿hay reservas sin confirmar para el sábado?",
            ),
        },
        "description": "Lists reservations: of some days (date_from, date_to) or, with `search` (a guest's name, phone "
        "or email), of the whole book; filters by status, table, customer, party size and time; in calendar order by "
        "default; pages of up to 100."
    },
)
def list_reservations(ctx: OperationContext, params: ReservationListIn) -> dict:
    asked = {lookup: getattr(params, field) for field, lookup in RESERVATION_FILTERS.items() if getattr(params, field)}
    rows = reservations().filter(**asked)
    if params.guest_name:
        rows = rows.filter(contains_text(params.guest_name, "guest_name"))
    if params.search:
        rows = rows.filter(_guest_matches(ctx, params.search))
    if params.guest_phone:
        rows = rows.filter(_phone_matches(params.guest_phone))
    if params.time:
        rows = rows.annotate(time_text=_hhmm("time")).filter(
            time_text__contains=params.time
        )
    return _page(
        rows.order_by(*list_order_for(params.sort, columns=RESERVATION_SORTS)),
        params,
        lambda reservation: reservation_out(ctx, reservation),
    )


@operation(
    "reservation.reservation.get",
    kind="query",
    permission="reservation.view_reservation",
    input=ReservationRefIn,
    output=ReservationDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what time is Luis's booking on Saturday?",
                "show me the details of Marta's reservation",
            ),
            "es": (
                "¿a qué hora es la reserva de Luis del sábado?",
                "dime los datos de la reserva de Marta",
                "¿cuántos vienen en la reserva de los Pérez?",
            ),
        },
        "description": "Reads one reservation with all its detail: by id, or by its guest's name or phone and its day "
        "(«Ana's reservation tomorrow»); without a day, her coming ones."
    },
)
def get_reservation(ctx: OperationContext, params: ReservationRefIn) -> dict:
    found = find_reservation(ctx, params.id, params.guest, params.day)
    return {**reservation_out(ctx, found), "label": reservation_label(ctx, found)}
