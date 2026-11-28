"""The business's cash register settings (CASH_REGISTER-F01), saved field by field."""

import datetime as dt

from django.db import IntegrityError
from live.context import OperationContext
from live.operations import atomic, operation
from live.outbox import record_event

from apps.cash_register import events
from apps.cash_register.models import Settings
from apps.cash_register.queries.people import actor
from apps.cash_register.queries.settings import settings_row
from apps.cash_register.schemas.settings import SettingsOut, SettingsPatchIn


def _locked_settings(ctx: OperationContext) -> tuple[Settings, bool]:
    """The business's settings row, locked, and whether this save made it (with the factory values)."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings, False
    try:
        with atomic():
            return Settings.objects.create(updated_by=actor(ctx)), True
    except IntegrityError:
        return Settings.objects.select_for_update().get(), False


@operation(
    "cash_register.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="cash_register.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "turn on the blind count",
                "close the till by itself every night at 3 am",
                "don't require a count to close the till",
            ),
            "es": (
                "activa el arqueo ciego",
                "que la caja se cierre sola cada noche a las 3",
                "configura la caja para cerrar sin contar el efectivo",
            ),
        },
        "description": "Change how the drawer works, field by field: cash register on, opening float required, count "
        "required to close, negative balance allowed, blind count, daily auto-close and its hour («04:00»). What is not "
        "sent is kept.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings, created = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    if "auto_close_time" in sent:
        sent["auto_close_time"] = dt.time.fromisoformat(sent["auto_close_time"])
    changes = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
    # The first save is the business's decision even with the factory values: the row and its date are born.
    if changes or created:
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)
