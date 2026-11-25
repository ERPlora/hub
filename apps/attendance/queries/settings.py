"""The time clock settings as they read: attendance.settings.get."""

from live.context import OperationContext
from live.operations import operation

from apps.attendance.schemas import EmptyIn, SettingsOut

from .reads import saved_settings, settings_values


@operation(
    "attendance.settings.get",
    kind="query",
    permission="attendance.clock",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what radius does the time clock allow?",
                "does clocking in from a phone ask for the location?",
                "after how many hours is a forgotten day flagged?",
            ),
            "es": (
                "dame el radio en metros para fichar con el móvil",
                "¿se pide la ubicación al fichar con el móvil?",
                "¿a partir de cuántas horas se avisa de un día olvidado?",
            ),
        },
        "description": "The time clock settings: whether a personal device must share its location and be "
        "within the workplace radius to clock in, the radius, the workplace and after how many hours a "
        "forgotten day is flagged for review."
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_values(saved_settings())
