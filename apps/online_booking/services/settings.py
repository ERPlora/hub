"""The page's settings (F07), with the diary's booking rules they carry."""

from live.context import OperationContext
from live.operations import get, operation
from live.outbox import record_event

from apps.appointment.schemas import settings as diary_settings
from apps.online_booking.events import SETTINGS_UPDATED
from apps.online_booking.models import Settings
from apps.online_booking.queries.settings import RULE_FIELDS, settings_out
from apps.online_booking.schemas.settings import SettingsIn, SettingsOut
from base.queries.people import actor_name

from .logo import check_logo

MANAGE = "online_booking.manage_settings"


def _actor(ctx: OperationContext) -> str:
    return actor_name(ctx.actor)[:128]


@operation(
    "online_booking.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "ask for an email when customers book by themselves",
                "change the welcome text customers see when they book",
            ),
            "es": (
                "pide el email a quien reserve por internet",
                "cambia el texto de bienvenida de la web de reservas",
            ),
        },
        "description": "Change the booking page's settings and the diary's booking rules it uses; only what is sent "
        "changes, all of it or nothing (e.g. switch the page on, ask for the email, or set the minimum notice).",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    rules = {field: value for field, value in sent.items() if field in RULE_FIELDS}
    settings = Settings.objects.select_for_update().first() or Settings()
    changed = {
        field: value
        for field, value in sent.items()
        if field not in RULE_FIELDS and getattr(settings, field) != value
    }
    if "logo" in changed:
        check_logo(ctx, changed["logo"])
    if changed:
        for field, value in changed.items():
            setattr(settings, field, value)
        settings.updated_by = _actor(ctx)
        settings.save()
        record_event(ctx, SETTINGS_UPDATED, {})
    if rules:
        # The diary's own operation, with the caller's right to change its settings: all or nothing.
        get("appointment.settings.update")(ctx, diary_settings.SettingsIn(**rules))
    return settings_out(ctx, settings)
