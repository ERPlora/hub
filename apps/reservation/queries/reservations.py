"""The reservations (``reservation.reservation.list``, ``.get``): those of some days or, searching, of the whole
book, and one reservation by its id or as a person says it.
"""

from django.db.models import CharField, F, Func, Value
from live.context import OperationContext
from live.operations import operation

from apps.reservation.queries.lookups import _guest_matches, _phone_matches, find_reservation
from apps.reservation.queries.rows import _page, reservation_label, reservation_out, reservations
from apps.reservation.schemas.reservations import (
    ReservationDetailOut,
    ReservationListIn,
    ReservationPage,
    ReservationRefIn,
)
from base.ordering import list_order_for

#: The list's filters that narrow by one column as they come: the input's field → its lookup.
RESERVATION_FILTERS = {
    "date_from": "date__gte",
    "date_to": "date__lte",
    "status": "status",
    "table_id": "table_id",
    "customer_id": "customer_id",
    "guest_name": "guest_name__icontains",
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


def _hhmm(field: str) -> Func:
    """A time column as ``HH:MM`` text, to filter it by part of what the screen shows («21»)."""
    return Func(F(field), Value("HH24:MI"), function="to_char", output_field=CharField())


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
