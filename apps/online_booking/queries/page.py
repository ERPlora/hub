"""What the public page shows of itself: whose it is, its texts and the booking rules it keeps."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import operation

from apps.appointment.queries.business import current_settings as current_rules
from apps.online_booking.schemas.fields import NoIn
from apps.online_booking.schemas.public import PageOut
from base.business import zone_name

from .settings import page_settings
from .visitors import PUBLIC

DEFAULT_TITLE = _("Book an appointment")


@operation(
    "online_booking.public.page",
    kind="query",
    permission=PUBLIC,
    input=NoIn,
    output=PageOut,
    ai={
        "asks": {
            "en": (
                "what do customers see when they open my booking link?",
                "show me the welcome text and colour of the self-booking screen",
            ),
            "es": (
                "¿qué aspecto tiene mi web de reservas para las clientas?",
                "enséñame el logo y la bienvenida que ve quien reserva por internet",
            ),
        },
        "description": "What the public booking page shows: whose it is, its title, texts, colour, logo and booking rules."
    },
)
def public_page(ctx: OperationContext, data: NoIn) -> dict:
    own = page_settings()
    rules = current_rules()
    return PageOut.owner(ctx, own.logo) | {
        "title": own.page_title or str(DEFAULT_TITLE),
        "welcome_message": own.welcome_message,
        "primary_color": own.primary_color,
        "require_email": own.require_email,
        "allow_staff_selection": own.allow_staff_selection,
        "allow_notes": own.allow_notes,
        "cancellation_policy": own.cancellation_policy,
        "min_booking_notice": rules.min_booking_notice,
        "max_advance_booking": rules.max_advance_booking,
        "allow_customer_cancellation": rules.allow_customer_cancellation,
        "cancellation_notice_hours": rules.cancellation_notice_hours,
        "timezone": zone_name(),
    }
