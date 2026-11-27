"""The settings (SCHEDULE-F08, F09): the day the week starts on, whether the week is confirmed and the business's
time zone."""

from live.context import OperationContext
from live.operations import operation

from apps.schedule.schemas.fields import NoParamsIn
from apps.schedule.schemas.settings import SettingsOut

from .outputs import settings_out
from .rows import settings_row


@operation(
    "schedule.settings.get",
    kind="query",
    permission="schedule.view",
    input=NoParamsIn,
    output=SettingsOut,
    ai={
        "description": "Returns the settings of the opening hours (the day the week starts on) and the business's "
        "time zone.",
        "asks": {
            "en": (
                "does our week start on Monday or on Sunday?",
                "which time zone is our calendar in?",
            ),
            "es": (
                "¿la semana del calendario arranca en lunes o en domingo?",
                "¿en qué zona horaria tenemos el calendario?",
            ),
        },
    },
)
def get_settings(ctx: OperationContext, data: NoParamsIn) -> dict:
    return settings_out(settings_row())
