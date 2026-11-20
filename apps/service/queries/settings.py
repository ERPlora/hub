"""The settings of the service app, as the reads show them and as the writes take them."""

from live.context import OperationContext
from live.operations import operation

from apps.service.models import ServiceSettings
from apps.service.schemas import NoIn, SettingsOut


def current_settings() -> ServiceSettings:
    """The business's settings; the factory ones (unsaved) if they were never saved."""
    return (
        ServiceSettings.objects.select_related("default_tax_category").first()
        or ServiceSettings()
    )


def settings_row(settings: ServiceSettings) -> dict:
    tax = settings.default_tax_category
    return {
        "default_duration": settings.default_duration,
        "default_buffer_time": settings.default_buffer_time,
        "default_tax_category_id": tax.id if tax else None,
        "default_tax_category_key": tax.key if tax else None,
        "default_tax_category_name": tax.display_name if tax else None,
        "show_prices": settings.show_prices,
        "show_duration": settings.show_duration,
        "allow_online_booking": settings.allow_online_booking,
        "updated_at": None if settings._state.adding else settings.updated_at,
    }


@operation(
    "service.settings.get",
    kind="query",
    permission="service.view_service",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The service settings: the duration, buffer, tax category and online booking a new service "
        "takes.",
        "asks": {
            "en": ("how long does a new service last by default?", "what buffer do new services get by default?"),
            "es": (
                "¿qué duración por defecto tiene un servicio nuevo?",
                "¿qué margen tienen por defecto los servicios?",
            ),
        },
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_row(current_settings())
