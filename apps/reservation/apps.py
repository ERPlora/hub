"""The reservation app: the restaurant's book of table reservations — the slots and the days it books,
each reservation from pending to completed with its table held on the floor plan, and the waitlist
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


class ReservationConfig(LiveAppConfig):
    name = "apps.reservation"
    label = "reservation"
    kind = "app"
    verbose_name = _("Reservations")
    # Registered in the shell (ION_ICONS); a restaurant table of its own waits in UI-REQUESTS.md.
    icon = "ion:calendar-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _(
        "Your book of table reservations: slots, covers, the table held for each guest and a waitlist."
    )
    description = _(
        "Reservations is the book of your restaurant or bar. Decide when you take bookings and how many "
        "fit in each slot, block the days you do not, and note every reservation by phone or at the door, "
        "linked to the guest's customer card. Follow each one from pending to confirmed, seated and "
        "completed: a confirmed reservation holds its table on the floor plan from an hour before, and "
        "seating it opens the table's check. Who could not get a table waits on the waitlist, ready to "
        "become a reservation in one tap."
    )
    verticals = ["restaurant"]
    # A reservation's table is a table of Tables (held on its floor plan), its guest a card of Customers,
    # and a booking fits the opening hours of Schedules.
    requires = ["table", "customer", "schedule"]
    default_auto_field = "django.db.models.BigAutoField"
    assistant_settings = ("reservation.settings.get",)
    permissions = {
        "reservation.view_reservation": _("View reservations"),
        "reservation.add_reservation": _("Take reservations"),
        "reservation.change_reservation": _("Change reservations and their status"),
        "reservation.delete_reservation": _("Delete reservations"),
        "reservation.view_timeslot": _("View time slots"),
        "reservation.change_timeslot": _("Create and remove time slots"),
        "reservation.view_blockeddate": _("View blocked dates"),
        "reservation.change_blockeddate": _("Block and unblock dates"),
        "reservation.view_waitlistentry": _("View the waiting list"),
        "reservation.change_waitlistentry": _("Change the waiting list"),
        "reservation.view_settings": _("View the settings"),
        "reservation.manage_settings": _("Change the settings"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The host at the
    # door is an employee: she takes, confirms, seats, edits and cancels reservations and keeps the
    # waitlist (WORKBOOK «Referencia adoptada», duda 1); the slots, blocked days and rules are the
    # manager's; deleting for good, the owner's and the admin's.
    role_permissions = {
        "hub_owner": ["reservation.*"],
        "hub_admin": ["reservation.*"],
        "hub_manager": [
            "reservation.view_reservation",
            "reservation.add_reservation",
            "reservation.change_reservation",
            "reservation.view_timeslot",
            "reservation.change_timeslot",
            "reservation.view_blockeddate",
            "reservation.change_blockeddate",
            "reservation.view_waitlistentry",
            "reservation.change_waitlistentry",
            "reservation.view_settings",
            "reservation.manage_settings",
        ],
        "hub_employee": [
            "reservation.view_reservation",
            "reservation.add_reservation",
            "reservation.change_reservation",
            "reservation.view_timeslot",
            "reservation.view_blockeddate",
            "reservation.view_waitlistentry",
            "reservation.change_waitlistentry",
            "reservation.view_settings",
        ],
    }
    # RESERVATION-F13: the pending reservations nobody confirmed are released a few minutes after their
    # time, every quarter of an hour, by the worker on every hub as the system (cron in UTC).
    scheduled_tasks = [
        {
            "name": "release_unconfirmed_reservations",
            "operation": "reservation.reservation.release_unconfirmed",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon. Each entry opens with its permission: Availability and Settings, to whoever may change
    # them.
    navigation = [
        Nav(
            "reservations",
            _("Reservations"),
            "ion:calendar-outline",
            "/reservation/reservations",
            permission="reservation.view_reservation",
        ),
        Nav(
            "waitlist", _("Waitlist"), "ion:people-outline", "/reservation/waitlist",
            permission="reservation.view_waitlistentry",
        ),
        Nav(
            "availability",
            _("Availability"),
            "ion:time-outline",
            "/reservation/availability",
            permission="reservation.change_timeslot",
        ),
        Nav(
            "settings", _("Settings"), "ion:settings-outline", "/reservation/settings",
            permission="reservation.manage_settings",
        ),
    ]
    help = Help()
