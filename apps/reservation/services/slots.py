"""The time slots the book takes reservations in (RESERVATION-F01)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.reservation import events
from apps.reservation.models import TimeSlot
from apps.reservation.queries.slots import find_slot, slot_out
from apps.reservation.schemas.fields import DeletedOut
from apps.reservation.schemas.slots import TimeSlotIn, TimeSlotOut, TimeSlotRefIn
from apps.reservation.services.gate import lock_book
from apps.reservation.services.writes import _stamp

SLOT_OVERLAPS = _("That slot overlaps another one of the same day (%(start)s–%(end)s).")


@operation(
    "reservation.time_slot.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_timeslot",
    input=TimeSlotIn,
    output=TimeSlotOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "add a booking slot on Saturdays from 1 pm to 4 pm",
                "take reservations on Sunday evenings from 8 to 11",
            ),
            "es": (
                "nueva franja de reservas: sábados de 13:00 a 16:00",
                "acepta reservas los domingos por la noche de 20:00 a 23:00",
            ),
        },
        "description": "Creates a slot the book takes reservations in: a weekday (0 = Monday … 6 = Sunday), from and "
        "to, how many reservations fit and, optionally, how many guests. Slots of a day never overlap.",
        "risk": "normal",
    },
)
def create_slot(ctx: OperationContext, data: TimeSlotIn) -> dict:
    lock_book()
    clash = (
        TimeSlot.objects.filter(
            is_deleted=False,
            day_of_week=data.day_of_week,
            start_time__lt=data.end_time,
            end_time__gt=data.start_time,
        )
        .order_by("start_time")
        .first()
    )
    if clash is not None:
        text = str(SLOT_OVERLAPS) % {
            "start": f"{clash.start_time:%H:%M}",
            "end": f"{clash.end_time:%H:%M}",
        }
        raise Conflict(
            text, code="reservation.slot_overlaps", fields={"start_time": text}
        )
    slot = TimeSlot(**data.model_dump())
    _stamp(slot, ctx, created=True)
    slot.save()
    record_event(ctx, events.TIME_SLOT_CREATED, {"id": str(slot.pk)})
    return slot_out(slot)


@operation(
    "reservation.time_slot.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_timeslot",
    input=TimeSlotRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "remove the Monday lunch slot",
                "stop taking bookings in the Sunday 8 pm slot",
            ),
            "es": (
                "quita la franja de los lunes a mediodía",
                "ya no damos cenas los domingos: borra esa franja de reservas",
            ),
        },
        "description": "Removes a slot (by id, or by its weekday and start): no more reservations are taken in it; the "
        "ones it had stay.",
        "risk": "high",
    },
)
def delete_slot(ctx: OperationContext, data: TimeSlotRefIn) -> dict:
    slot = find_slot(data.id, data.day_of_week, data.start_time, lock=True)
    slot.is_deleted, slot.deleted_at = True, timezone.now()
    _stamp(slot, ctx)
    slot.save()
    record_event(ctx, events.TIME_SLOT_DELETED, {"id": str(slot.pk)})
    return {"id": slot.pk}
