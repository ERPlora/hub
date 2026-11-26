"""The settings (SCHEDULE-F08): the day the week of the hours starts on."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.schedule import events
from apps.schedule.queries.outputs import settings_out
from apps.schedule.schemas.settings import SettingsIn, SettingsOut

from .writes import _locked_settings


@operation(
    "schedule.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="schedule.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    ai={
        "description": "Changes the day the opening week starts on (1 = Monday … 7 = Sunday): only the order of the "
        "week's table, never an hour.",
        "risk": "normal",
        "asks": {
            "en": (
                "start the week on Sunday on the calendar",
                "I want the week to begin on Monday",
            ),
            "es": (
                "cambia el inicio de semana al lunes",
                "ordena la semana del calendario empezando por el domingo",
            ),
        },
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    """SCHEDULE-F08: the first save creates the row; only a change says so."""
    row = _locked_settings()
    if data.week_starts_on is not None and data.week_starts_on != row.week_starts_on:
        row.week_starts_on = data.week_starts_on
        row.save(update_fields=["week_starts_on", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(row)
