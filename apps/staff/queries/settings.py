"""The default working day a new schedule proposes (STAFF-F22)."""

from live.context import OperationContext
from live.operations import operation

from apps.staff.models import StaffSettings
from apps.staff.schemas.settings import SettingsGetIn, SettingsOut


@operation(
    "staff.settings.get",
    kind="query",
    permission="staff.view",
    input=SettingsGetIn,
    output=SettingsOut,
    ai={
        "asks": {
            "en": (
                "what working day does a new schedule propose by default?",
                "what are the default shift hours?",
                "which break does a new schedule suggest?",
            ),
            "es": (
                "¿qué jornada propone por defecto un horario nuevo?",
                "¿cuál es el horario por defecto de los turnos?",
                "¿cuánto descanso trae por defecto un turno recién creado?",
            ),
        },
        "description": "Returns the default working day that a new schedule proposes (start, end and break)."
    },
)
def get_settings(ctx: OperationContext, data: SettingsGetIn) -> dict:
    """The saved settings, or the defaults while the business has saved none (STAFF-F22)."""
    return settings_out(saved_settings())


def saved_settings() -> StaffSettings:
    """The business's row, or the defaults (not saved) while it has saved none."""
    return StaffSettings.objects.first() or StaffSettings()


def settings_out(row: StaffSettings) -> dict:
    """The settings as the screen shows them: hours as HH:MM, never with seconds."""
    return {
        **{field: getattr(row, field) for field in SettingsOut.model_fields},
        "default_work_start": row.default_work_start.strftime("%H:%M"),
        "default_work_end": row.default_work_end.strftime("%H:%M"),
    }
