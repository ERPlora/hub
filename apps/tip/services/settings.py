"""Saving the tip settings (TIP-F01): only what is sent changes, and saving the same records nothing."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.sale.queries.business import actor
from apps.sale.queries.payment_methods import find_method
from apps.tip import events
from apps.tip.models import Settings
from apps.tip.queries import FACTORY_SUGGESTIONS, settings_row
from apps.tip.schemas import SettingsOut, SettingsPatchIn

FLAGS = ("enabled", "allow_custom", "preselected")


def _suggestions(settings: Settings, data: SettingsPatchIn) -> dict | None:
    """The suggestions by payment method once ``data``'s are in, or ``None`` when they change none."""
    suggestions = dict(settings.suggestions)
    for entry in data.methods or []:
        method = find_method(entry.method_id, None)
        suggestions[str(method.id)] = [suggestion.model_dump() for suggestion in entry.suggestions]
    changed = any(
        suggestions[key] != settings.suggestions.get(key, FACTORY_SUGGESTIONS) for key in suggestions
    )
    return suggestions if changed else None


@operation(
    "tip.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tip.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("ask for a tip at the charge", "suggest 1 €, 2 € and 5 € as tips when paying by card"),
            "es": ("pide propina al cobrar", "con tarjeta sugiere de propina 1 €, 2 € y 5 €"),
        },
        "description": "Change the tip settings, only in what is sent: whether a tip is asked for at the charge, which "
        "of the three suggestions comes chosen (0: «No tip»), whether another amount is allowed, and the three "
        "suggestions of a payment method, each a percentage (1 to 100) or an amount in cents, none twice.",
        "risk": "normal",
        "check": "tip.settings.get",
    },
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = Settings.objects.select_for_update().first() or Settings()
    changed = [field for field in FLAGS if getattr(data, field) is not None and getattr(data, field) != getattr(settings, field)]
    for field in changed:
        setattr(settings, field, getattr(data, field))
    suggestions = _suggestions(settings, data)
    if suggestions is not None:
        settings.suggestions = suggestions
        changed.append("methods")
    if changed:
        settings.updated_by = actor(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {"changed": sorted(changed)})
    return settings_row(settings)
