"""The appointment app: the salon's diary — who comes, for what, with whom and when."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy
from live.meta import BellCounter, Category, DeviceNotice, Help, LiveAppConfig, Nav, SetupCheck

from apps.appointment.events import TO_CONFIRM_EVENTS

#: What may add a notice: a booking, and a cancellation (the query keeps the customer's own).
NOTICE_EVENTS = ["appointment.appointment.created", "appointment.appointment.cancelled"]
#: The notice's body: the services, «{day} at {hour}» and the professional.
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
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). A «bloqueo» of the agenda is its blocked
    # period (appointment.blocked_time), as «block» says in English; a «cita fija», a «serie semanal» or a «cita que se
    # repite» is a repeating appointment (appointment.recurring), named by its phrases and never by «serie» alone, which
    # is also an invoice's series; whether someone «puede atender» or there is a «hueco libre» asks for the availability
    # of the agenda (appointment.availability), named by its phrases: «puede» and «libre» alone ask for nothing.
    assistant_synonyms = (
        ("bloqueo", "blocked"),
        (
            "recurring", "cita fija", "citas fijas", "cita periodica", "citas periodicas", "cita semanal",
            "citas semanales", "cita mensual", "citas mensuales", "serie semanal", "series semanales", "serie mensual",
            "serie quincenal", "serie de citas", "series de citas", "que se repite", "que se repiten", "que se repita",
            "que se repitan", "repeating appointment", "repeating appointments", "weekly appointment",
            "monthly appointment",
        ),
        (
            "availability", "puede atender", "pueda atender", "puede coger", "pueda coger", "hueco libre",
            "huecos libres",
        ),
    )
    permissions = {
        "appointment.view_appointment": _("View the whole appointment book"),
        "appointment.view_own_appointment": _("View their own appointment book"),
        "appointment.add_appointment": _("Book appointments for anyone"),
        "appointment.add_own_appointment": _("Book appointments in their own appointment book"),
        "appointment.change_appointment": _("Change any appointment: status, move, cancel, charge and series"),
        "appointment.change_own_appointment": _("Change their own appointments"),
        "appointment.delete_appointment": _("Delete appointments"),
        "appointment.view_schedule": _("View availability and blocked time"),
        "appointment.manage_schedule": _("Block time"),
        "appointment.manage_settings": _("Change the settings"),
    }
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
    # as the module's own icon.
    # The entry's label is the tab bar's: the help window and the assistant name the screen by it.
    navigation = [
        Nav(
            "appointments",
            _("Agenda"),
            "ion:calendar-outline",
            "/appointment/agenda",
            permission="appointment.view_own_appointment",
        ),
        Nav(
            "settings", _("Settings"), "ion:settings-outline", "/appointment/settings",
            permission="appointment.manage_settings",
        ),
    ]
    help = Help(
        videos={"es": "iDYOJPslKLo", "en": "T9O2qIaHX38"},
        flow_videos={
            "APPOINTMENT-F01": {"es": ["7k8rDOavPPQ"], "en": ["jqE5frTxwIs"]},
            "APPOINTMENT-F02": {"es": ["7k8rDOavPPQ"], "en": ["jqE5frTxwIs"]},
            "APPOINTMENT-F03": {"es": ["JEZ7xwTUQRg"], "en": ["_IJqA5Llo58"]},
            "APPOINTMENT-F04": {"es": ["3iicsBB4OJU"], "en": ["vti0BeNrB0A"]},
            "APPOINTMENT-F07": {"es": ["SCCcOjjX0-Q"], "en": ["5RkcBExG2Sc"]},
            "APPOINTMENT-F08": {"es": ["SCCcOjjX0-Q"], "en": ["5RkcBExG2Sc"]},
            "APPOINTMENT-F09": {"es": ["lyPRKIKNyzE"], "en": ["_7B2JQ7NPCM"]},
            "APPOINTMENT-F22": {"es": ["3iicsBB4OJU"], "en": ["vti0BeNrB0A"]},
        },
    )
    # The bell counts the customers' own bookings waiting for confirmation, on the query the agenda's «N to
    # confirm» reads (whoever sees an agenda counts her own, or everybody's when she sees them all).
    bell = [
        BellCounter(
            key="to_confirm",
            operation="appointment.appointment.count_to_confirm",
            route="/appointment/agenda",
            label=_("Appointments to confirm"),
            icon="ion:calendar-outline",
            permission="appointment.view_own_appointment",
            refresh_on=TO_CONFIRM_EVENTS,
            severity="warning",
            title=ngettext_lazy("%(count)d appointment to confirm", "%(count)d appointments to confirm", "count"),
            body=ngettext_lazy(
                "A customer is waiting for you to confirm their booking before it starts.",
                "Customers are waiting for you to confirm their bookings before they start.",
                "count",
            ),
            action_label=_("Confirm the appointments"),
            # The start of the soonest one: it has to be confirmed before then.
            due="earliest",
        )
    ]
    # The device is told what the customer booked or cancelled herself, of the agenda the person sees (the
    # query's rules: never the front desk's, an employee only hears her own).
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

    def recoverable_from_copy(self) -> list:
        """The platform asks (``base.tenancy.recovery``) what a separate copy of the business gives back when the staff
        recovers from it: of the copy's appointments still to come and booked (``recovery.appointments_in_copy``), each
        the business still holds deleted comes back the same, with its number, its history and its series
        (``recovery.appointments_deleted_in_business``, ``appointment.appointment.restore``), and each it no longer has
        is created by ``appointment.appointment.create``, the agenda's own, for the business's card of its customer
        (``recovery.appointments_not_in_business``); what does not fit the agenda now (its time taken, outside the
        hours, a customer, a service or a professional it no longer has) is refused with why, never booked over another.

        Then its series still booking (``recovery.series_in_copy``), after the appointments so that none of their dates
        is booked twice: each the business holds deleted comes back the same, active, with the appointments it had
        booked and booking nothing by itself (``recovery.series_deleted_in_business``,
        ``appointment.recurring.restore``), and each it no longer has is created by ``appointment.recurring.create``,
        Repeating's own (``recovery.series_not_in_business``); one made again since stays as it is."""
        from apps.appointment.queries import recovery  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=self.verbose_name,
                reads_since="0001_initial",
                read=recovery.appointments_in_copy,
                missing=recovery.appointments_not_in_business,
                create="appointment.appointment.create",
                deleted=recovery.appointments_deleted_in_business,
                restore="appointment.appointment.restore",
            ),
            Recoverable(
                label=_("Repeating appointments"),
                reads_since="0001_initial",
                read=recovery.series_in_copy,
                missing=recovery.series_not_in_business,
                create="appointment.recurring.create",
                deleted=recovery.series_deleted_in_business,
                restore="appointment.recurring.restore",
            ),
        ]
