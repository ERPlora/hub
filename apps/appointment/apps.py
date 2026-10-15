"""The appointment app: the salon's diary — who comes, for what, with whom and when."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class AppointmentConfig(LiveAppConfig):
    name = "apps.appointment"
    label = "appointment"
    kind = "app"
    verbose_name = _("Appointments")
    icon = "ion:calendar-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Your diary: appointments by professional, free times, repeating bookings and charging them at the till."
    )
    description = _(
        "Appointments is the diary of a business that works by appointment. Each booking joins a customer, "
        "one or more services and a professional at a time that fits the opening hours, the professional's "
        "shift and time off, and no other booking of theirs. See the day or the week by professional, drag a "
        "booking to move it, confirm, start, complete or cancel it, keep repeating bookings, let customers "
        "book and cancel within your rules, and charge a booking at the till without typing it again."
    )
    # A hair salon books from sign-up; a restaurant's template does not carry it.
    verticals = ["hair_salon"]
    # The customer of a booking, its services, its professional and the business's opening hours.
    # (The README's and the erplora-apps skill's example omit `schedule`: the diary reads the hours.)
    requires = ["customer", "service", "staff", "schedule"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "appointment.view_appointment",
        "appointment.view_own_appointment",
        "appointment.add_appointment",
        "appointment.add_own_appointment",
        "appointment.change_appointment",
        "appointment.change_own_appointment",
        "appointment.delete_appointment",
        "appointment.view_schedule",
        "appointment.manage_schedule",
        "appointment.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The employee sees
    # and manages their own diary; the manager everybody's; owner and admin also delete and set it up.
    role_permissions = {
        "hub_owner": ["appointment.*"],
        "hub_admin": ["appointment.*"],
        "hub_manager": [
            "appointment.view_appointment",
            "appointment.view_own_appointment",
            "appointment.add_appointment",
            "appointment.add_own_appointment",
            "appointment.change_appointment",
            "appointment.change_own_appointment",
            "appointment.view_schedule",
            "appointment.manage_schedule",
        ],
        "hub_employee": [
            "appointment.view_own_appointment",
            "appointment.add_own_appointment",
            "appointment.change_own_appointment",
            "appointment.view_schedule",
        ],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon. The old module's single entry (`calendar-outline`).
    navigation = [
        Nav(
            "appointments",
            _("Appointments"),
            "ion:calendar-outline",
            "/appointment/agenda",
        ),
    ]
