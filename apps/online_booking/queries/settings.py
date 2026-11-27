"""The page's settings, with the diary's booking rules it shows, and whether the page takes bookings."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.appointment.queries.business import current_settings as current_rules
from apps.online_booking.models import Settings
from apps.online_booking.schemas.fields import NoIn
from apps.online_booking.schemas.settings import SettingsOut
from base.business import zone_name

from .bookings import VIEW

PAGE_DISABLED = _("This business does not take online bookings right now.")

_OWN_FIELDS = (
    "is_enabled",
    "page_title",
    "welcome_message",
    "primary_color",
    "require_email",
    "max_upcoming_per_customer",
    "allow_staff_selection",
    "allow_notes",
    "confirmation_message",
    "cancellation_policy",
)
#: The diary's rules the page shows and the settings change (Citas' settings).
RULE_FIELDS = (
    "min_booking_notice",
    "max_advance_booking",
    "slot_interval",
    "auto_confirm_online",
    "allow_customer_cancellation",
    "cancellation_notice_hours",
)


def current_settings() -> Settings:
    """The saved settings, or the factory ones (unsaved: the page off) while nobody saved them."""
    return Settings.objects.first() or Settings()


def page_settings(*, lock: bool = False) -> Settings:
    """The settings of a page that takes bookings; 404 ``online_booking.page_disabled`` while it is off.

    ``lock`` takes the settings row until the end of the command's transaction: the public bookings of the hub
    then run one after another, so their limits (per visitor, per business, per mobile) and the card of a new
    mobile are decided on what the previous booking wrote.
    """
    settings = (Settings.objects.select_for_update().first() if lock else Settings.objects.first()) or Settings()
    if not settings.is_enabled:
        raise NotFound(str(PAGE_DISABLED), code="online_booking.page_disabled")
    return settings


def settings_out(ctx: OperationContext, own: Settings) -> dict:
    rules = current_rules()
    return {
        **{field: getattr(own, field) for field in _OWN_FIELDS},
        **SettingsOut.logo_of(ctx.scope, own.logo),
        **{field: getattr(rules, field) for field in RULE_FIELDS},
        "timezone": zone_name(),
    }


@operation(
    "online_booking.settings.get",
    kind="query",
    permission=VIEW,
    input=NoIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how is my self-booking set up?",
                "do customers have to give an email to book by themselves?",
            ),
            "es": (
                "¿cómo tengo puesta la reserva por internet?",
                "¿la web de reservas obliga a dejar el email?",
            ),
        },
        "description": "The booking page's settings (on or off, title, texts, colour, logo, email required, choose "
        "the professional, notes, upcoming bookings per customer) and the diary's booking rules it uses (minimum "
        "notice, maximum advance, slot interval, auto-confirm, customer cancellation and its notice)."
    },
)
def get_settings(ctx: OperationContext, data: NoIn) -> dict:
    return settings_out(ctx, current_settings())
