"""The online booking app: the door through which a customer books herself, and the inbox where the business
confirms what she booked. The booking is an appointment of the diary (source «online»)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, LiveAppConfig, Nav


class OnlineBookingConfig(LiveAppConfig):
    name = "apps.online_booking"
    label = "online_booking"
    kind = "app"
    # With a context: Citas translates «Online booking» as one booking's origin («Reserva online»).
    verbose_name = pgettext_lazy("app name", "Online booking")
    icon = "ion:globe-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Let customers book themselves online, and confirm or cancel their bookings from one inbox."
    )
    description = _(
        "Online booking is your booking page: customers pick a service, a professional or anyone free, a day "
        "and a free time, leave their name and mobile, and the booking goes straight into your diary, confirmed "
        "or waiting for you to confirm it. Their link lets them see and cancel it within your cancellation "
        "policy. From the inbox you confirm, complete, mark no-shows and cancel; in the settings you choose the "
        "page's texts and colours, the booking rules and which services can be booked online."
    )
    verticals = ["hair_salon"]
    # The booking is an appointment (Citas); its customer is a card (Clientes); the catalog and who does each
    # service, Servicios and Personal.
    requires = ["appointment", "customer", "service", "staff"]
    default_auto_field = "django.db.models.BigAutoField"
    # ``public`` is the public door's (the page without a session, served by base); owner and admin hold it
    # too, to preview the page.
    permissions = [
        "online_booking.view_booking",
        "online_booking.change_booking",
        "online_booking.confirm_booking",
        "online_booking.delete_booking",
        "online_booking.manage_settings",
        "online_booking.public",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["online_booking.*"],
        "hub_admin": ["online_booking.*"],
        "hub_manager": [
            "online_booking.view_booking",
            "online_booking.change_booking",
            "online_booking.confirm_booking",
        ],
        "hub_employee": ["online_booking.view_booking"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =` as the
    # module's own icon. The old module's two entries.
    navigation = [
        Nav(
            "bookings",
            _("Bookings"),
            "ion:calendar-outline",
            "/online_booking/bookings",
        ),
        Nav(
            "settings",
            _("Settings"),
            "ion:settings-outline",
            "/online_booking/settings",
        ),
    ]
