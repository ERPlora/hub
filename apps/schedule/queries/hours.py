"""The hours of a range of days (SCHEDULE-F11): the rule of each day and its opening spans, what the appointment
book crosses with each professional's availability."""

import datetime as dt

from live.context import OperationContext
from live.operations import operation

from apps.schedule import engine
from apps.schedule.schemas.hours import HoursRangeIn, HoursRangeOut
from base.business import zone_name

from .outputs import intervals_out
from .rows import load_calendar


@operation(
    "schedule.hours.for_range",
    kind="query",
    permission="schedule.view",
    input=HoursRangeIn,
    output=HoursRangeOut,
    expose_api=True,
    ai={
        "description": "Returns the business's opening hours of each day of a range (up to 366 days): the rule that "
        "governs the day and its opening spans as wall-clock date and time. A booking fits when it lies inside one "
        "span of its day or of the eve (past midnight). The authoritative answer to when the business is open.",
        "asks": {
            "en": (
                "what are our opening times for every date from 1 to 15 December?",
                "which rule sets our opening on every date of next month?",
            ),
            "es": (
                "¿cuándo abrimos cada día entre el 1 y el 15 de diciembre?",
                "¿de dónde sale la apertura de cada día del mes que viene?",
                "dime día a día cuándo abrimos la próxima quincena",
            ),
        },
    },
)
def hours_for_range(ctx: OperationContext, data: HoursRangeIn) -> dict:
    """SCHEDULE-F11: what the appointment book crosses with each professional's availability (staff)."""
    date_to = data.date_to or data.date_from
    calendar = load_calendar(data.date_from, date_to)
    days = []
    for offset in range((date_to - data.date_from).days + 1):
        day = data.date_from + dt.timedelta(days=offset)
        rule = engine.rule_for(calendar, day)
        days.append(
            {
                "date": day,
                "source": rule.source,
                "rule_id": rule.rule_id,
                "name": rule.name,
                "is_closed": rule.is_closed,
                "intervals": intervals_out(rule.intervals),
                "spans": [
                    {"start": start, "end": end}
                    for start, end in engine.spans_of(rule, day)
                ],
            }
        )
    return {"timezone": zone_name(), "days": days}
