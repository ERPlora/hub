"""The history of corrections of the working days (attendance.correction.list), and the reason the system writes
when a termination in Staff closes a day."""

from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.attendance.models import Correction, Record
from apps.attendance.schemas import CorrectionListIn, CorrectionPage

from .days import visible_record
from .reads import VIEW_ALL, _own_days, _page

#: The reason of the system's correction when a termination closes a day (ATTENDANCE-F13). Stored in
#: English, the source, and shown in the reader's language.
TERMINATED_REASON = _("Day closed when the person was terminated in Staff.")
TERMINATED_REASON_SOURCE = "Day closed when the person was terminated in Staff."
SYSTEM_REASONS = frozenset({TERMINATED_REASON_SOURCE})


def correction_out(trail: Correction) -> dict:
    system = trail.is_system
    return {
        "id": trail.id,
        "record_id": trail.record_id,
        "old_clock_in_at": trail.old_clock_in_at,
        "old_clock_out_at": trail.old_clock_out_at,
        "old_status": trail.old_status,
        "new_clock_in_at": trail.new_clock_in_at,
        "new_clock_out_at": trail.new_clock_out_at,
        "new_status": trail.new_status,
        # A system reason is stored in English and read in the reader's language.
        "reason": gettext(trail.reason)
        if system and trail.reason in SYSTEM_REASONS
        else trail.reason,
        "is_system": system,
        # The name copied when the correction was made: it outlives the user.
        "created_by_name": trail.created_by_name,
        "created_at": trail.created_at,
    }


@operation(
    "attendance.correction.list",
    kind="query",
    permission="attendance.clock",
    input=CorrectionListIn,
    output=CorrectionPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who corrected Elena's working day?",
                "show me this week's corrections of clock-ins",
                "what was changed in yesterday's clock-in and why?",
            ),
            "es": (
                "¿quién corrigió la jornada de Elena?",
                "muéstrame las correcciones de fichajes de esta semana",
                "¿qué se cambió en el fichaje de ayer y por qué?",
            ),
        },
        "description": "The history of corrections of a working day (or of all of them): the times before "
        "and after, the reason, who and when, newest first. An employee sees the history of their own days."
    },
)
def list_corrections(ctx: OperationContext, params: CorrectionListIn) -> dict:
    trails = Correction.objects.all()
    if params.record_id is not None:
        trails = trails.filter(record=visible_record(ctx, params.record_id))
    elif not ctx.has(VIEW_ALL):
        own = _own_days(ctx)
        trails = (
            trails.filter(record__in=Record.objects.filter(own))
            if own is not None
            else trails.none()
        )
    trails = trails.order_by("-created_at", "-id")
    rows = [
        correction_out(t) for t in trails[params.offset : params.offset + params.limit]
    ]
    return _page(rows, trails.count(), params)
