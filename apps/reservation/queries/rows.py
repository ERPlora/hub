"""What a read answers of a record: its row, a page of rows and, read by id, its ``label``: the words the book's
screens name it by, which the assistant's card says instead of the id (schemas/fields.py, ``names``).
"""

import datetime as dt

from babel.dates import format_date, format_time
from django.db.models import QuerySet
from live.context import OperationContext

from apps.customer.queries.contact import sees_contact
from apps.reservation.models import (
    BlockedDate,
    Reservation,
    TimeSlot,
    WaitlistEntry,
    weekday_name,
)
from apps.reservation.queries.clock import wall_clock, window_of
from apps.schedule.queries import day_label
from apps.table.queries import floor
from base.business import babel_locale


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


def entry_out(entry: WaitlistEntry) -> dict:
    return {
        "id": entry.pk,
        "customer_id": entry.customer_id,
        "guest_name": entry.guest_name,
        "guest_phone": entry.guest_phone,
        "guest_email": entry.guest_email,
        "date": entry.date,
        "preferred_time": entry.preferred_time,
        "party_size": entry.party_size,
        "notes": entry.notes,
        "is_contacted": entry.is_contacted,
        "contacted_at": entry.contacted_at,
        "is_converted": entry.reservation_id is not None,
        "reservation_id": entry.reservation_id,
        "created_at": entry.created_at,
    }


def slot_out(slot: TimeSlot) -> dict:
    return {
        "id": slot.pk,
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "max_reservations": slot.max_reservations,
        "max_covers": slot.max_covers,
    }


def blocked_out(block: BlockedDate) -> dict:
    return {
        "id": block.pk,
        "date": block.date,
        "reason": block.reason,
        "is_full_day": block.is_full_day,
        "blocked_from": block.blocked_from,
        "blocked_until": block.blocked_until,
    }


def _page(queryset, params, row) -> dict:
    total = queryset.count()
    window = queryset[params.offset : params.offset + params.limit]
    return {
        "rows": [row(item) for item in window],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


# ── How the book names a record (a read by id's ``label``) ──────────────────────────────────────
# In the words the assistant's card says a day and a time (base/assistant/cards.py: CLDR's medium day and short
# time, as the screens' formatters), in the caller's language: «Ana García · 15 oct 2026 · 21:00».


def _said_day(day: dt.date, language: str) -> str:
    return format_date(day, "medium", locale=babel_locale(language))


def _said_time(at: dt.time, language: str) -> str:
    return format_time(at.replace(tzinfo=None), "short", locale=babel_locale(language))


def _said_hours(start: dt.time, end: dt.time, language: str) -> str:
    return f"{_said_time(start, language)}–{_said_time(end, language)}"


def _named(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def _who(ctx: OperationContext, row: Reservation | WaitlistEntry) -> str:
    """The guest as the dialogs say her: her name, else her phone to whoever sees it; nothing once erased."""
    return row.guest_name or (row.guest_phone if sees_contact(ctx) else "")


def reservation_label(ctx: OperationContext, reservation: Reservation) -> str:
    """As the book's dialogs say a reservation before a step: its guest, its day and its time."""
    return _named(_who(ctx, reservation), _said_day(reservation.date, ctx.language), _said_time(reservation.time, ctx.language))


def entry_label(ctx: OperationContext, entry: WaitlistEntry) -> str:
    """As the waitlist's dialogs say an entry: its guest, the day and the time they would like."""
    return _named(_who(ctx, entry), _said_day(entry.date, ctx.language), _said_time(entry.preferred_time, ctx.language))


def slot_label(slot: TimeSlot, language: str) -> str:
    """As the slots' list says a slot: its weekday and its hours («Jueves · 20:00–23:30»)."""
    return _named(weekday_name(slot.day_of_week, language), _said_hours(slot.start_time, slot.end_time, language))


def blocked_label(block: BlockedDate, language: str) -> str:
    """As the blocked dates' list says one: its day and, when it blocks only some hours, those hours."""
    hours = (
        ""
        if block.is_full_day
        else _said_hours(block.blocked_from, block.blocked_until, language)
    )
    return _named(_said_day(block.date, language), hours)
