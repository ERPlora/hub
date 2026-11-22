"""The book's rules (RESERVATION-F03, F04)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import operation
from live.outbox import record_event

from apps.reservation import events
from apps.reservation.queries import settings_row
from apps.reservation.schemas import SettingsIn, SettingsOut
from apps.reservation.services.gate import lock_book
from apps.reservation.services.writes import actor_label

MIN_ABOVE_MAX = _("The minimum guests cannot be more than the maximum.")


@operation(
    "reservation.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="reservation.manage_settings",
    input=SettingsIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the reservation settings to take bookings 30 days ahead",
                "enable automatic confirmation for reservations",
            ),
            "es": (
                "deja reservar con hasta 30 días de antelación",
                "haz que las reservas se confirmen solas",
            ),
        },
        "description": "Changes the book's rules: fewest and most guests, notice for online and WhatsApp, days ahead, "
        "default duration, automatic confirmation, phone or email required, and the minutes after which an unconfirmed "
        "reservation is released. Only what is sent changes.",
        "risk": "normal",
    },
)
def update_settings(ctx: OperationContext, data: SettingsIn) -> dict:
    settings = lock_book()
    changes = {
        field: value for field, value in data.model_dump(exclude_none=True).items()
    }
    for field, value in changes.items():
        setattr(settings, field, value)
    if settings.min_party_size > settings.max_party_size:
        raise InvalidPayload(
            str(MIN_ABOVE_MAX), fields={"min_party_size": str(MIN_ABOVE_MAX)}
        )
    if changes:
        settings.updated_by = actor_label(ctx)
        settings.save()
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)
