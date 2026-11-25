"""Settings (KITCHEN-F26)."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.kitchen import events
from apps.kitchen.queries.reads import settings_out
from apps.kitchen.schemas.settings import SettingsOut, SettingsPatchIn
from apps.kitchen.services.settling import settle
from apps.kitchen.services.writes import actor, locked_settings

AMBER_FIRST = _("The amber warning has to come before the red one.")


@operation(
    "kitchen.settings.update",
    kind="command",
    permission="kitchen.change_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "mute the display",
                "make the display go red sooner",
            ),
            "es": (
                "pon más bajo el sonido de la pantalla",
                "que la pantalla avise antes en ámbar",
            ),
        },
        "description": "Change the kitchen display settings (only what is sent): the clock, the amber and red minutes, "
        "the sound and its tone and volume, the pass on paper, whether the kitchen works from the screen, the "
        "default ticket type.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    row = locked_settings()
    # What the settings in force already decide (a round served by paper) is saved before they change:
    # switching the screen back on never brings a charged round back «To prepare».
    settle(ctx, row)
    sent = {
        name: value
        for name, value in data.model_dump(exclude_unset=True).items()
        if value is not None
    }
    warning = sent.get("warning_minutes", row.warning_minutes)
    critical = sent.get("critical_minutes", row.critical_minutes)
    if warning >= critical:
        fields = {
            name: str(AMBER_FIRST)
            for name in ("warning_minutes", "critical_minutes")
            if name in sent
        }
        raise InvalidPayload(str(AMBER_FIRST), code="invalid_field", fields=fields)
    changed = sorted(
        name for name, value in sent.items() if getattr(row, name) != value
    )
    if "works_from_screen" in changed:
        row.screen_changed_at = timezone.now()
    for name in changed:
        setattr(row, name, sent[name])
    row.updated_by = actor(ctx)
    row.save()
    if changed:
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": changed})
    return settings_out(row)
