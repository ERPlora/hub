"""The book's rules as they are read (``reservation.settings.get``) and as a change of them answers.
"""

from live.context import OperationContext
from live.operations import operation

from apps.reservation.models import Settings
from apps.reservation.queries.gate import current_settings
from apps.reservation.schemas.fields import NoIn
from apps.reservation.schemas.settings import SettingsOut
from base.business import zone_name


def settings_row(settings: Settings) -> dict:
    return {
        "min_party_size": settings.min_party_size,
        "max_party_size": settings.max_party_size,
        "min_advance_hours": settings.min_advance_hours,
        "max_advance_days": settings.max_advance_days,
        "default_duration_minutes": settings.default_duration_minutes,
        "auto_confirm": settings.auto_confirm,
        "require_phone": settings.require_phone,
        "require_email": settings.require_email,
        "no_show_window_minutes": settings.no_show_window_minutes,
        "timezone": zone_name(),
    }


@operation(
    "reservation.settings.get",
    kind="query",
    permission="reservation.view_settings",
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how far ahead can guests book?",
                "are reservations confirmed automatically?",
            ),
            "es": (
                "¿qué antelación piden los ajustes de reservas?",
                "¿las reservas se confirman solas?",
            ),
        },
        "description": "Reads the book's rules: guests per reservation, notice and days ahead, default duration, "
        "automatic confirmation, phone or email required, when an unconfirmed reservation is released, and the "
        "business's time zone."
    },
)
def get_settings(ctx: OperationContext, params: NoIn) -> dict:
    return settings_row(current_settings())
