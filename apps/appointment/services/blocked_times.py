"""The blocked times of the diary (APPOINTMENT-F16)."""

import datetime as dt

from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation
from live.outbox import record_event

from apps.appointment import engine, events
from apps.appointment.models import BlockedTime
from apps.appointment.queries import (
    BLOCK_NOT_FOUND,
    blocked_out,
    business_zone,
    read_moment,
)
from apps.appointment.schemas import (
    BlockedTimeCreateIn,
    BlockedTimeOut,
    BlockedTimeRefIn,
    DeletedOut,
)
from apps.appointment.services.writes import _actor
from apps.staff.queries import resolve_member

MANAGE_SCHEDULE = "appointment.manage_schedule"


@operation(
    "appointment.blocked_time.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SCHEDULE,
    input=BlockedTimeCreateIn,
    output=BlockedTimeOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "block the agenda on Christmas Eve",
                "block Inés's Friday afternoon for a training",
            ),
            "es": (
                "bloquea la agenda el día de Nochebuena",
                "bloquea la tarde del viernes de Inés por una formación",
            ),
        },
        "description": "Block a period of the agenda (a holiday, a training, a professional's break): for the whole "
        "business or one professional (by name), between two wall-clock times or whole days (all_day). Nobody books it.",
        "risk": "normal",
    },
)
def create_blocked_time(ctx: OperationContext, data: BlockedTimeCreateIn) -> dict:
    member = (
        resolve_member(data.staff_id, data.staff)
        if (data.staff_id or data.staff)
        else None
    )
    zone = business_zone()
    if data.all_day:
        first = engine.wall(read_moment(data.start, "start"), zone).date()
        last = engine.wall(read_moment(data.end, "end"), zone).date()
        start, end = (
            engine.midnight(first, zone),
            engine.midnight(last + dt.timedelta(days=1), zone),
        )
    else:
        start, end = read_moment(data.start, "start"), read_moment(data.end, "end")
    block = BlockedTime.objects.create(
        title=data.title,
        block_type=data.block_type,
        start=start,
        end=end,
        all_day=data.all_day,
        staff=member,
        reason=data.reason,
        created_by=_actor(ctx),
    )
    record_event(
        ctx,
        events.BLOCKED_TIME_CREATED,
        {"id": str(block.id), "staff_id": str(member.id) if member else None},
    )
    return blocked_out(block)


@operation(
    "appointment.blocked_time.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SCHEDULE,
    input=BlockedTimeRefIn,
    output=DeletedOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "remove the block on Friday afternoon",
                "unblock the agenda on Christmas Eve",
            ),
            "es": (
                "quita el bloqueo del viernes por la tarde",
                "desbloquea la agenda de Nochebuena",
            ),
        },
        "description": "Remove a blocked period: its time can be booked again. One the person names by its title or "
        "its day is found with appointment.blocked_time.list, from today on when no day is said.",
        "risk": "high",
    },
)
def delete_blocked_time(ctx: OperationContext, data: BlockedTimeRefIn) -> dict:
    block = BlockedTime.objects.select_for_update().filter(pk=data.id).first()
    if block is None:
        raise NotFound(str(BLOCK_NOT_FOUND), code="appointment.blocked_time_not_found")
    block.delete()
    record_event(ctx, events.BLOCKED_TIME_DELETED, {"id": str(data.id)})
    return {"id": data.id}
