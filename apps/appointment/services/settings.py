"""The settings of the diary (APPOINTMENT-F19)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.appointment import events
from apps.appointment.models import Settings
from apps.appointment.queries import settings_out
from apps.appointment.schemas import SettingsIn, SettingsOut
from apps.appointment.services.writes import _actor

MANAGE_SETTINGS = "appointment.manage_settings"
CALENDAR_UPSIDE_DOWN = _("The calendar has to end after it starts.")


@operation(
    "appointment.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE_SETTINGS,
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "require two hours' notice to book an appointment",
                "stop auto-confirming the appointments customers book",
            ),
            "es": (
                "pide al menos un día de antelación para las citas",
                "que las citas de las clientas no se confirmen solas",
            ),
        },
        "description": "Change the booking rules; only what is sent changes (e.g. turn off auto-confirming the "
        "customer's own bookings, or set the minimum notice).",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    settings = Settings.objects.select_for_update().first() or Settings()
    sent = {
        field: getattr(data, field)
        for field in data.model_fields_set
        if getattr(data, field) is not None
    }
    start = sent.get("calendar_start_hour", settings.calendar_start_hour)
    end = sent.get("calendar_end_hour", settings.calendar_end_hour)
    if end <= start:
        message = str(CALENDAR_UPSIDE_DOWN)
        field = (
            "calendar_end_hour"
            if "calendar_end_hour" in sent
            else "calendar_start_hour"
        )
        raise InvalidPayload(message, fields={field: message})
    changed = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changed:
        for field, value in changed.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {})
    return settings_out(settings)
