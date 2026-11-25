"""What the system runs: the review of forgotten days and closing the open day of a terminated person."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.attendance.models import Record
from apps.attendance.queries.corrections import TERMINATED_REASON_SOURCE
from apps.attendance.queries.days import load_record
from apps.attendance.queries.reads import saved_settings, settings_values
from apps.attendance.schemas import ClosedOut, EmptyIn, ReviewOut, TerminatedIn
from apps.staff.models import Member

from .corrections import _correct
from .days import TICK, _end_break, _flag_stale, _open_day


@operation(
    "attendance.record.review_stale",
    kind="command",
    permission="attendance.correct",
    input=EmptyIn,
    output=ReviewOut,
    ai={
        "asks": {
            "en": (
                "flag the forgotten clock-outs for review",
                "check now for days nobody closed",
                "mark the working days left open too long",
            ),
            "es": (
                "deja pendientes las jornadas que nadie cerró a tiempo",
                "comprueba si alguien se olvidó de fichar la salida",
                "señala las jornadas abiertas desde hace demasiado",
            ),
        },
        "description": "Flags for review every working day still open after the hours of the settings "
        "(a forgotten clock-out). It never invents a clock-out. The scheduled task runs it every 15 minutes.",
        "risk": "normal",
    },
)
def review_stale(ctx: OperationContext, data: EmptyIn) -> dict:
    hours = settings_values(saved_settings())["auto_close_after_hours"]
    flagged = _flag_stale(ctx, Record.objects.all(), hours, timezone.now())
    return {"flagged": len(flagged), "record_ids": flagged}


@operation(
    "attendance.record.close_for_terminated",
    kind="command",
    permission="attendance.correct",
    input=TerminatedIn,
    output=ClosedOut,
    ai={
        "asks": {
            "en": (
                "close the open day of the person I just terminated",
                "Luis no longer works here: close his open clock-in",
                "we let Nuria go: close the working day she left open",
            ),
            "es": (
                "cierra la jornada abierta de quien acabo de despedir",
                "Luis ya no trabaja aquí, cierra su fichaje abierto",
                "la empleada que se fue dejó el día abierto: ciérralo",
            ),
        },
        "description": "Closes, at this moment and with a correction of the system, the open working day of "
        "a staff member who was terminated in Staff (its reaction to staff.member.terminated).",
        "risk": "normal",
    },
)
def close_for_terminated(ctx: OperationContext, data: TerminatedIn) -> dict:
    # Only a terminated record: a stray or replayed call for anyone else changes nothing.
    member = (
        Member.objects.select_for_update(no_key=True)
        .filter(pk=data.id, status=Member.Status.TERMINATED)
        .first()
    )
    record = _open_day(member) if member is not None else None
    if record is None:
        return {"record": None}
    record = Record.objects.select_for_update().get(pk=record.pk)
    now = timezone.now()
    out = now if now > record.clock_in_at else record.clock_in_at + TICK
    _end_break(ctx, record, out)
    _correct(ctx, record, record.clock_in_at, out, TERMINATED_REASON_SOURCE)
    return {"record": load_record(record.id, now)}
