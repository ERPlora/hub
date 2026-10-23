"""The appointment app: the salon's diary — who comes, for what, with whom and when."""

from django.utils.translation import gettext_lazy as _
from live.meta import BellCounter, Category, DeviceNotice, LiveAppConfig, Nav, SetupCheck

from apps.appointment.events import TO_CONFIRM_EVENTS

#: What may add a notice: a booking, and a cancellation (the query keeps the customer's own).
NOTICE_EVENTS = ["appointment.appointment.created", "appointment.appointment.cancelled"]
#: The old shell's body (old-hub:HUB_SHELL-F66): the services, «{day} at {hour}» and the professional.
NOTICE_BODY = ["{service_names}", _("{start_date_label} at {start_time_label}"), "{staff_name}"]
#: A tap opens the agenda on the appointment's day (its start, on the business's clock).
NOTICE_ROUTE = "/appointment/agenda?date={start:.10}"


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
    # The Home's hooks (PLAN-HUB round 2026-10-21): the old module's counter of the bell, the customers' own bookings
    # waiting for confirmation, on the query the agenda's «N to confirm» reads (whoever sees an agenda counts her
    # own, or everybody's when she sees them all). No steps of «Finish setting up your business» nor panels of the
    # dashboard: the old module had none.
    bell = [
        BellCounter(
            key="to_confirm",
            operation="appointment.appointment.count_to_confirm",
            route="/appointment/agenda",
            label=_("Appointments to confirm"),
            icon="ion:calendar-outline",
            permission="appointment.view_own_appointment",
            refresh_on=TO_CONFIRM_EVENTS,
        )
    ]
    # APPOINTMENT-F28 (old-hub:HUB_SHELL-F66): the device is told what the customer booked or cancelled herself, of
    # the agenda the person sees (the query's rules: never the front desk's, an employee only hears her own).
    notices = [
        DeviceNotice(
            key="booked",
            operation="appointment.appointment.notices",
            when=[SetupCheck(field="kind", equals="booked")],
            title=[_("New appointment · {customer_name}"), _("New appointment")],
            body=NOTICE_BODY,
            route=NOTICE_ROUTE,
            permission="appointment.view_own_appointment",
            refresh_on=NOTICE_EVENTS,
        ),
        DeviceNotice(
            key="cancelled",
            operation="appointment.appointment.notices",
            when=[SetupCheck(field="kind", equals="cancelled")],
            title=[_("Appointment cancelled · {customer_name}"), _("Appointment cancelled")],
            body=NOTICE_BODY,
            route=NOTICE_ROUTE,
            permission="appointment.view_own_appointment",
            refresh_on=NOTICE_EVENTS,
        ),
    ]
