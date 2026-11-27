"""The settings of the room (TABLE-F08)."""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import atomic, operation
from live.outbox import record_event

from apps.table import events
from apps.table.models import TableSettings
from apps.table.queries.settings import current_settings, settings_row
from apps.table.schemas.settings import SettingsIn, SettingsOut
from apps.table.services.writes import actor_label

RED_BEFORE_AMBER = _("The red warning cannot come before the amber one.")


def _settings_row_locked() -> TableSettings:
    """The settings' one row, locked; created with the factory values the first time. Two first saves at
    once: the second one's row loses to the unique single row, and it takes the first one's, locked."""
    settings = TableSettings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return TableSettings.objects.create()
    except IntegrityError:
        return TableSettings.objects.select_for_update().get()


@operation(
    "table.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="table.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Change the room settings: whether seating asks for the guests, and after how many minutes an "
        "open check turns amber and red. Only what is sent changes.",
        "risk": "normal",
        "asks": {
            "en": (
                "make tables turn red after 45 minutes",
                "stop asking for guests when seating",
            ),
            "es": (
                "que las mesas se pongan rojas a los 45 minutos",
                "no preguntes los comensales al sentar",
            ),
        },
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    changes = {
        field: value for field, value in data.model_dump(exclude_none=True).items()
    }
    settings = _settings_row_locked() if changes else current_settings()
    for field, value in changes.items():
        setattr(settings, field, value)
    if settings.timer_critical_minutes < settings.timer_warning_minutes:
        raise InvalidPayload(
            str(RED_BEFORE_AMBER),
            fields={"timer_critical_minutes": str(RED_BEFORE_AMBER)},
        )
    if changes:
        settings.updated_by = actor_label(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)
