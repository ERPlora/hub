"""The reservation app: the restaurant's book of table reservations — the slots and the days it books,
each reservation from pending to completed with its table held on the floor plan, and the waitlist
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class ReservationConfig(LiveAppConfig):
    name = "apps.reservation"
    label = "reservation"
    kind = "app"
    verbose_name = _("Reservations")
    # The old module's first menu icon, registered in the shell (ION_ICONS); a restaurant table of its
    # own waits in UI-REQUESTS.md.
    icon = "ion:calendar-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
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
    # The old module's twelve permissions (module.json), renamed <app>.<action>.
    permissions = [
        "reservation.view_reservation",
        "reservation.add_reservation",
        "reservation.change_reservation",
        "reservation.delete_reservation",
        "reservation.view_timeslot",
        "reservation.change_timeslot",
        "reservation.view_blockeddate",
        "reservation.change_blockeddate",
        "reservation.view_waitlistentry",
        "reservation.change_waitlistentry",
        "reservation.view_settings",
        "reservation.manage_settings",
    ]
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
    # time, every quarter of an hour, by the phase-2 worker on every hub as the system (cron in UTC).
    scheduled_tasks = [
        {
            "name": "release_unconfirmed_reservations",
            "operation": "reservation.reservation.release_unconfirmed",
            "cron": "*/15 * * * *",
            "catch_up": "collapse",
        }
    ]
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =`
    # as the module's own icon. The old module's three sections with its icons; Settings is a tab of
    # the pages (frontend/tabs.ts), shown only to whoever may save them.
    navigation = [
        Nav(
            "reservations",
            _("Reservations"),
            "ion:calendar-outline",
            "/reservation/reservations",
        ),
        Nav("waitlist", _("Waitlist"), "ion:people-outline", "/reservation/waitlist"),
        Nav(
            "availability",
            _("Availability"),
            "ion:time-outline",
            "/reservation/availability",
        ),
    ]
