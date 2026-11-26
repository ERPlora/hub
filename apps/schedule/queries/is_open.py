"""Is it open? (SCHEDULE-F10): the engine's verdict at a moment, on the business's own clock."""

from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.schedule import engine
from apps.schedule.schemas.is_open import IsOpenIn, IsOpenOut
from base.business import business_zone, zone_name

from .rows import load_calendar


@operation(
    "schedule.business.is_open",
    kind="query",
    permission="schedule.view",
    input=IsOpenIn,
    output=IsOpenOut,
    expose_api=True,
    ai={
        "description": "Says whether the business is open at a moment (now if none) on its own clock, which rule "
        "decided (special day > yearly special day > temporary change > usual week > nothing) and why, as a stable "
        "code: exception_closed, exception_hours, open_interval, closed_today, overnight_open, outside_hours or "
        "no_hours (nothing configured: not open).",
        "asks": {
            "en": (
                "is the shop open right now?",
                "will the shop be open tomorrow at nine?",
            ),
            "es": (
                "¿seguimos abiertos todavía?",
                "¿el local estará abierto mañana a las nueve?",
                "¿está cerrado el local en este momento?",
            ),
        },
    },
)
def business_is_open(ctx: OperationContext, data: IsOpenIn) -> dict:
    """SCHEDULE-F10; the rules are the server's own, the caller only says when."""
    moment = engine.parse_when(data.when, business_zone(), timezone.now())
    verdict = engine.is_open(load_calendar(moment.date(), moment.date()), moment)
    return {
        "is_open": verdict.is_open,
        "code": verdict.code,
        "source": verdict.source,
        "rule_id": verdict.rule_id,
        "intervals": verdict.intervals,
        "timezone": zone_name(),
        "today": moment.date(),
        "current_time": f"{moment:%H:%M}",
        "reason": verdict.reason or None,
    }
