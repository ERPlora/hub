"""Live queries of the appointment app and the events that re-run them after the COMMIT.

The agenda is live: a booking, a move, a state change, a charge or an unassignment re-runs what shows
appointments; the free times also follow the blocks, the settings and other apps' changes of hours
(Schedules), shifts and time off (Staff) and who performs a service (Services). The time's verdict
(``availability.check``) is asked at the moment of acting: not followed.
"""

from live.live_registry import live

from apps.appointment.events import (
    APPOINTMENT_EVENTS,
    BLOCKED_TIME_EVENTS,
    RECURRING_EVENTS,
    SCHEDULE_EVENTS,
    SERVICE_EVENTS,
    SETTINGS_UPDATED,
    STAFF_EVENTS,
)

#: A card merged or erased changes whose appointments and series these are, or the names they show.
CUSTOMER_GONE = ["customer.customer.merged", "customer.customer.erased"]
AVAILABILITY = [
    *APPOINTMENT_EVENTS,
    *BLOCKED_TIME_EVENTS,
    SETTINGS_UPDATED,
    *SCHEDULE_EVENTS,
    *STAFF_EVENTS,
    *SERVICE_EVENTS,
]

live("appointment.appointment.list", on=APPOINTMENT_EVENTS)
live("appointment.appointment.get", on=APPOINTMENT_EVENTS)
live("appointment.appointment.history", on=APPOINTMENT_EVENTS)
live(
    "appointment.appointment.list_for_customer",
    on=[*APPOINTMENT_EVENTS, *CUSTOMER_GONE],
)
live(
    "appointment.appointment.count_active_for_service",
    on=[*APPOINTMENT_EVENTS, "service.service.archived"],
)
live("appointment.appointment.count_to_confirm", on=APPOINTMENT_EVENTS)
# What the customer did herself; an erased card empties the name it shows.
live("appointment.appointment.notices", on=[*APPOINTMENT_EVENTS, *CUSTOMER_GONE])
# A professional kept on the agenda, or a new one taking bookings, changes its rows.
live("appointment.agenda.lanes", on=[*APPOINTMENT_EVENTS, *STAFF_EVENTS])
live("appointment.availability.slots", on=AVAILABILITY)
# A block shows its professional's name.
live("appointment.blocked_time.list", on=[*BLOCKED_TIME_EVENTS, *STAFF_EVENTS])
# A series shows its services' names.
live(
    "appointment.recurring.list",
    on=[*RECURRING_EVENTS, *CUSTOMER_GONE, "service.service.updated"],
)
live(
    "appointment.recurring.get",
    on=[*RECURRING_EVENTS, *APPOINTMENT_EVENTS, *CUSTOMER_GONE],
)
live("appointment.settings.get", on=[SETTINGS_UPDATED])
