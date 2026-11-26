"""The usual week (SCHEDULE-F01): the seven days, from the one the settings say."""

from live.context import OperationContext
from live.operations import operation

from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.week import WeekOut

from .outputs import week_out


@operation(
    "schedule.week.get",
    kind="query",
    permission="schedule.view",
    input=NoParamsIn,
    output=WeekOut,
    expose_api=True,
    ai={
        "description": "Returns the business's usual opening week: each day closed, not set or with its opening "
        "intervals (several = split shift; closing before opening = past midnight; 00:00–00:00 = 24 hours), and "
        "whether the week is still the default one nobody confirmed.",
        "asks": {
            "en": (
                "show me when we usually open, Monday to Sunday",
                "which weekdays are we normally closed?",
            ),
            "es": (
                "enséñame cuándo abrimos habitualmente, de lunes a domingo",
                "¿cuándo descansamos normalmente?",
                "¿cuándo solemos abrir y cerrar de lunes a viernes?",
            ),
        },
    },
)
def get_week(ctx: OperationContext, data: NoParamsIn) -> dict:
    """SCHEDULE-F01: the seven days, from the one the settings say."""
    return week_out()
