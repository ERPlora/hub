"""The breaks inside the open working day: attendance.break.start and .end."""

from django.db import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import atomic, operation
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import Break
from apps.attendance.queries.days import load_record
from apps.attendance.schemas import BreakIn, RecordOut

from .days import _day_now, _end_break, _not_clocked_in, _target

BREAK_RUNNING = _("A break is already running.")
NO_BREAK_RUNNING = _("There is no running break to end.")


@operation(
    "attendance.break.start",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.clock",
    input=BreakIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "I'm going on my lunch break",
                "put Luis on a break",
                "start a break for me",
            ),
            "es": (
                "me voy a comer, empieza mi pausa",
                "inicia una pausa para Luis",
                "me tomo cinco minutos de descanso",
            ),
        },
        "description": "Starts a break inside the open working day of the caller, or of the person named: puts "
        "them on a break («I'm going on a break»).",
        "check": "attendance.person.check",
        "risk": "normal",
    },
)
def start_break(ctx: OperationContext, data: BreakIn) -> dict:
    member, _mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None:
        raise _not_clocked_in()
    running = Conflict(str(BREAK_RUNNING), code="attendance.break_running")
    if Break.objects.filter(record=record, ended_at__isnull=True).exists():
        raise running
    try:
        with atomic():
            pause = Break.objects.create(
                record=record, started_at=max(now, record.clock_in_at)
            )
    except IntegrityError:
        raise running from None
    record_event(
        ctx,
        events.BREAK_STARTED,
        {"id": str(pause.id), "record_id": str(record.id), "member_id": str(member.id)},
    )
    return load_record(record.id, now)


@operation(
    "attendance.break.end",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="attendance.clock",
    input=BreakIn,
    output=RecordOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "I'm back from my break",
                "end Luis's break",
                "back to work after lunch",
            ),
            "es": (
                "se acabó mi pausa, vuelvo al trabajo",
                "acaba el descanso de Luis",
                "vuelvo de comer, sigo con mi jornada",
            ),
        },
        "description": "Ends the running break of the caller, or of the person named («I'm back»).",
        "check": "attendance.person.check",
        "risk": "normal",
    },
)
def end_break(ctx: OperationContext, data: BreakIn) -> dict:
    member, _mine = _target(ctx, data)
    now = timezone.now()
    record = _day_now(member, now)
    if record is None or not _end_break(ctx, record, now):
        raise Conflict(str(NO_BREAK_RUNNING), code="attendance.no_break_running")
    return load_record(record.id, now)
