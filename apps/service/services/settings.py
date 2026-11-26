"""The settings of the service app (SERVICE-F11)."""

from live.context import OperationContext
from live.operations import operation
from live.outbox import record_event

from apps.service import events
from apps.service.models.settings import ServiceSettings
from apps.service.queries.settings import settings_row
from apps.service.schemas.settings import SettingsIn, SettingsOut
from apps.service.services.writes import _apply, _changes, _tax_category


@operation(
    "service.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="service.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "Save the service settings: only the fields sent change. The duration, buffer, online booking "
        "and tax category are what a new service takes when it does not say them.",
        "risk": "high",
        "asks": {
            "en": (
                "change the services settings: 45 minutes by default",
                "leave ten minutes between services by default",
            ),
            "es": (
                "que los servicios nuevos duren una hora por defecto",
                "en los ajustes de servicios, pon diez minutos de margen",
            ),
        },
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    _, created = ServiceSettings.objects.get_or_create(singleton=True)
    settings = (
        ServiceSettings.objects.select_for_update(of=("self",))
        .select_related("default_tax_category")
        .get(singleton=True)
    )
    sent = data.model_fields_set
    values = {
        field: getattr(data, field)
        for field in (
            "default_duration",
            "default_buffer_time",
            "show_prices",
            "show_duration",
            "allow_online_booking",
        )
        if field in sent and getattr(data, field) is not None
    }
    if "default_tax_category_key" in sent:
        key = data.default_tax_category_key
        values["default_tax_category"] = (
            _tax_category(key, "default_tax_category_key", hold=True) if key else None
        )
    changes = _changes(settings, values)
    if changes or created:
        _apply(settings, changes, ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED)
    return settings_row(settings)
