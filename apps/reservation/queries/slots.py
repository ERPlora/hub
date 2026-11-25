"""The slots the book takes reservations in: the list, and one by id or by its weekday and its start."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.reservation.models import TimeSlot, weekday_name
from apps.reservation.queries.naming import _named, _said_hours
from apps.reservation.queries.reads import _page
from apps.reservation.schemas.slots import TimeSlotDetailOut, TimeSlotListIn, TimeSlotPage, TimeSlotRefIn
from base.ordering import list_order_for

SLOT_NOT_FOUND = _("That time slot does not exist in this business.")


def slot_out(slot: TimeSlot) -> dict:
    return {
        "id": slot.pk,
        "day_of_week": slot.day_of_week,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "max_reservations": slot.max_reservations,
        "max_covers": slot.max_covers,
    }


def slot_label(slot: TimeSlot, language: str) -> str:
    """As the slots' list says a slot: its weekday and its hours («Jueves · 20:00–23:30»)."""
    return _named(weekday_name(slot.day_of_week, language), _said_hours(slot.start_time, slot.end_time, language))


def find_slot(
    slot_id: UUID | None,
    day_of_week: int | None,
    start_time: dt.time | None,
    *,
    lock: bool = False,
) -> TimeSlot:
    """A live slot by id or by its weekday and its start."""
    rows = TimeSlot.objects.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    if slot_id is not None:
        rows = rows.filter(pk=slot_id)
    else:
        rows = rows.filter(day_of_week=day_of_week, start_time=start_time)
    slot = rows.first()
    if slot is None:
        raise NotFound(str(SLOT_NOT_FOUND), code="reservation.slot_not_found")
    return slot


SLOT_SORTS = {
    "day_of_week": ("day_of_week", "start_time"),
    "start_time": ("start_time", "day_of_week"),
    "end_time": ("end_time", "day_of_week"),
    "max_reservations": ("max_reservations",),
}


@operation(
    "reservation.time_slot.list",
    kind="query",
    permission="reservation.view_timeslot",
    input=TimeSlotListIn,
    output=TimeSlotPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what booking slots do we have?",
                "at what times do we take reservations on weekends?",
            ),
            "es": (
                "lista las franjas horarias de la semana",
                "¿en qué horarios aceptamos reservas los fines de semana?",
            ),
        },
        "description": "Lists the slots the book takes reservations in (weekday 0 = Monday … 6 = Sunday, from, to, "
        "maximum reservations and guests), by weekday and start."
    },
)
def list_slots(ctx: OperationContext, params: TimeSlotListIn) -> dict:
    rows = TimeSlot.objects.filter(is_deleted=False)
    if params.day_of_week is not None:
        rows = rows.filter(day_of_week=params.day_of_week)
    return _page(rows.order_by(*list_order_for(params.sort, columns=SLOT_SORTS)), params, slot_out)


@operation(
    "reservation.time_slot.get",
    kind="query",
    permission="reservation.view_timeslot",
    input=TimeSlotRefIn,
    output=TimeSlotDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many bookings fit in the Saturday 8 pm slot?",
                "show me the Sunday lunch slot",
            ),
            "es": (
                "¿cuántas reservas caben en la franja del domingo a las 13:30?",
                "enséñame la franja del domingo a mediodía",
            ),
        },
        "description": "Reads one slot the book takes reservations in: by id, or by its weekday (0 = Monday … 6 = "
        "Sunday) and its start."
    },
)
def get_slot(ctx: OperationContext, params: TimeSlotRefIn) -> dict:
    slot = find_slot(params.id, params.day_of_week, params.start_time)
    return {**slot_out(slot), "label": slot_label(slot, ctx.language)}
