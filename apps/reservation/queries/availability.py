"""A service day and the free tables (``reservation.availability.day``, ``.tables``), counted exactly as booking
counts them.
"""

import datetime as dt

from django.db.models import Count, Q, Sum
from live.context import OperationContext
from live.operations import operation

from apps.reservation.queries.clock import business_now, wall_clock, window_of
from apps.reservation.queries.gate import blocks_of, booked_windows, counted, current_settings, hours_of, slots_of
from apps.reservation.queries.rows import blocked_out
from apps.reservation.schemas.availability import DayIn, DayOut, FreeTablesOut, TablesIn
from apps.table.models import Table
from apps.table.queries import floor, natural_key
from base.business import zone_name


@operation(
    "reservation.availability.day",
    kind="query",
    permission="reservation.view_reservation",
    input=DayIn,
    output=DayOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many covers are booked today?",
                "how does Saturday night look for bookings?",
                "is there still room to book on Sunday?",
            ),
            "es": (
                "¿cuántos cubiertos tenemos reservados hoy?",
                "¿cómo vamos de reservas el sábado por la noche?",
                "¿queda hueco para reservar el domingo?",
            ),
        },
        "description": "How a service day looks (today if no date): its covers and reservations, whether it is blocked, "
        "the business's opening hours, and each slot with its reservations, guests, maximum and what is left (full or "
        "not, inside the opening hours or not). Counts exactly what booking checks."
    },
)
def day_availability(ctx: OperationContext, params: DayIn) -> dict:
    today = business_now().date()
    day = params.date or today
    blocks = blocks_of(day)
    hours = hours_of(ctx, day)
    slots = slots_of(day)
    totals = counted(day).aggregate(reservations=Count("id"), covers=Sum("party_size"))
    return {
        "date": day,
        "today": today,
        "timezone": zone_name(),
        "closed": any(block.is_full_day for block in blocks),
        "blocks": [blocked_out(block) for block in blocks],
        "hours_restricted": hours.restricted,
        # A night past midnight belongs to the day it opens: the eve's tail still counts for booking.
        "spans": [{"start": start, "end": end} for start, end in hours.spans if start.date() == day],
        "slots": [
            {
                "id": slot.id,
                "start_time": slot.start,
                "end_time": slot.end,
                "max_reservations": slot.max_reservations,
                "max_covers": slot.max_covers,
                "reserved": slot.reserved,
                "covers": slot.covers,
                "available": slot.available,
                "full": slot.full,
                "in_hours": hours.open_at(dt.datetime.combine(day, slot.start)),
            }
            for slot in slots
        ],
        "reservations": totals["reservations"] or 0,
        "covers": totals["covers"] or 0,
    }


@operation(
    "reservation.availability.tables",
    kind="query",
    permission="reservation.view_reservation",
    input=TablesIn,
    output=FreeTablesOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "where can I seat a party of four on Friday at 9 pm?",
                "what is still free for a booking of six tomorrow at 21:00?",
            ),
            "es": (
                "¿qué mesa le doy a una reserva de cuatro el viernes a las 21:00?",
                "¿tengo la mesa 5 libre para reservar mañana a las 21:00?",
            ),
        },
        "description": "The tables in service for a day, time and party: whether each one is free then (no live "
        "reservation overlaps the stay) and whether the party fits its seats; free and fitting first. Use it to pick "
        "the table of a reservation («is table 5 free tomorrow at 21?»)."
    },
)
def free_tables(ctx: OperationContext, params: TablesIn) -> dict:
    minutes = params.duration_minutes or current_settings().default_duration_minutes
    window = window_of(params.date, params.time, minutes)
    exclude = (params.exclude_id,) if params.exclude_id else ()
    tables = Table.objects.filter(
        is_deleted=False, is_active=True, blocked=False
    ).select_related("zone")
    tables = tables.filter(
        Q(zone__isnull=True) | Q(zone__is_active=True, zone__is_deleted=False)
    )
    if params.search:
        said = params.search.strip()
        tables = tables.filter(
            Q(number__icontains=said)
            | Q(name__icontains=said)
            | Q(zone__name__icontains=said)
        )
    out = []
    for table in tables.order_by(natural_key("number"), "id"):
        clash = booked_windows(table.pk, window, exclude)
        fits = params.party_size is None or table.capacity >= params.party_size
        out.append(
            {
                "id": table.pk,
                "number": table.number,
                "label": floor.table_label(table),
                "zone_name": table.zone.name if table.zone_id else "",
                "capacity": table.capacity,
                "fits": fits,
                "free": not clash,
                "taken_from": wall_clock(clash[0][1].start).time() if clash else None,
                "taken_until": wall_clock(clash[0][1].end).time() if clash else None,
            }
        )
    out.sort(key=lambda row: (not row["free"], not row["fits"]))
    return {"rows": out}
