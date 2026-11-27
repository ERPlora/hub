"""The settings as they are read."""

from live.context import OperationContext
from live.operations import operation

from apps.appointment.models.settings import Settings
from apps.appointment.schemas.fields import NoIn
from apps.appointment.schemas.settings import SettingsOut
from base.business import zone_name

from .access import VIEW_OWN
from .business import current_settings


def settings_out(settings: Settings) -> dict:
    fields = (
        "default_duration",
        "min_booking_notice",
        "max_advance_booking",
        "allow_overlapping",
        "allow_customer_cancellation",
        "cancellation_notice_hours",
        "calendar_start_hour",
        "calendar_end_hour",
        "slot_interval",
        "auto_confirm_online",
    )
    return {
        **{field: getattr(settings, field) for field in fields},
        "timezone": zone_name(),
    }


@operation(
    "appointment.settings.get",
    kind="query",
    permission=VIEW_OWN,
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what are our appointment booking rules?",
                "what's the minimum notice for an appointment?",
            ),
            "es": (
                "¿qué antelación mínima piden las citas?",
                "¿cómo están puestas las reglas de las citas?",
            ),
        },
        "description": "The appointments' settings, their booking rules: default length, minimum notice and maximum "
        "advance, overlaps, the customer's cancellation policy, the calendar window, the slot interval and whether "
        "the customer's own bookings are confirmed automatically; and the business's time zone."
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_out(current_settings())
