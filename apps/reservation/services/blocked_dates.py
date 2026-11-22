"""The blocked days and hours, when no reservations are taken (RESERVATION-F02)."""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.reservation import events
from apps.reservation.models import BlockedDate
from apps.reservation.queries import find_block, blocked_out
from apps.reservation.schemas import BlockedDateIn, BlockedDateOut, BlockedDateRefIn, DeletedOut
from apps.reservation.services.writes import _stamp

BLOCK_EXISTS = _("That date is already blocked at that time.")


@operation(
    "reservation.blocked_date.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_blockeddate",
    input=BlockedDateIn,
    output=BlockedDateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "block bookings on 24 December",
                "close reservations next Monday evening for a private event",
            ),
            "es": (
                "bloquea el día de Año Nuevo para que nadie reserve",
                "bloquea el lunes por la noche para un evento privado",
            ),
        },
        "description": "Blocks a day for reservations (a holiday, a closure, a private event), whole or only some hours "
        "(from, until). The reservations it already had stay.",
        "risk": "normal",
    },
)
def create_blocked(ctx: OperationContext, data: BlockedDateIn) -> dict:
    block = BlockedDate(
        date=data.date,
        reason=data.reason,
        is_full_day=data.is_full_day,
        blocked_from=None if data.is_full_day else data.blocked_from,
        blocked_until=None if data.is_full_day else data.blocked_until,
    )
    _stamp(block, ctx, created=True)
    try:
        with atomic():
            block.save()
    except IntegrityError:
        raise Conflict(
            str(BLOCK_EXISTS),
            code="reservation.blocked_date_exists",
            fields={"date": str(BLOCK_EXISTS)},
        ) from None
    record_event(
        ctx,
        events.BLOCKED_DATE_CREATED,
        {"id": str(block.pk), "date": block.date.isoformat()},
    )
    return blocked_out(block)


@operation(
    "reservation.blocked_date.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.change_blockeddate",
    input=BlockedDateRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "unblock 24 December for bookings",
                "remove the block of the holiday closure",
            ),
            "es": (
                "desbloquea el 24 de diciembre",
                "ya no cerramos por vacaciones, quita ese bloqueo",
                "borra el bloqueo del día de Navidad",
            ),
        },
        "description": "Unblocks a blocked date (by id, or by its date when it is blocked once): reservations are taken "
        "again. A block named by its reason («the Christmas closure») is found in reservation.blocked_date.list.",
        "risk": "high",
    },
)
def delete_blocked(ctx: OperationContext, data: BlockedDateRefIn) -> dict:
    block = find_block(data.id, data.date, lock=True)
    block.is_deleted, block.deleted_at = True, timezone.now()
    _stamp(block, ctx)
    block.save()
    record_event(
        ctx,
        events.BLOCKED_DATE_DELETED,
        {"id": str(block.pk), "date": block.date.isoformat()},
    )
    return {"id": block.pk}
