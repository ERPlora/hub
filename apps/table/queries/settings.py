"""The room settings (``table.settings.get``): the factory ones (unsaved) until they are saved."""

from live.context import OperationContext
from live.operations import operation

from apps.table.models import TableSettings
from .floor import RESERVED_LEAD
from apps.table.schemas.fields import NoIn
from apps.table.schemas.settings import SettingsOut
from base.business import zone_name


def current_settings() -> TableSettings:
    """The room settings; the factory ones (unsaved) if they were never saved."""
    return TableSettings.objects.first() or TableSettings()


def settings_row(settings: TableSettings) -> dict:
    return {
        "prompt_guests_on_seat": settings.prompt_guests_on_seat,
        "timer_warning_minutes": settings.timer_warning_minutes,
        "timer_critical_minutes": settings.timer_critical_minutes,
        "reserved_lead_minutes": int(RESERVED_LEAD.total_seconds() // 60),
        "timezone": zone_name(),
    }


@operation(
    "table.settings.get",
    kind="query",
    permission="table.view_settings",
    input=NoIn,
    output=SettingsOut,
    ai={
        "description": "Read the room settings: whether seating asks for the guests and when an open check turns "
        "amber and red.",
        "asks": {
            "en": (
                "when does a table turn red?",
                "how long until a table shows amber?",
                "does seating ask how many guests?",
            ),
            "es": (
                "¿a partir de cuántos minutos se pone en rojo una mesa?",
                "¿cuándo se pone una mesa en ámbar?",
                "¿al sentar se preguntan los comensales?",
            ),
        },
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_row(current_settings())
