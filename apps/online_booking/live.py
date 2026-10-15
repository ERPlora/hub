"""Live queries of the online booking app and the events that re-run them after the COMMIT.

The inbox is live: any change of an appointment of the diary (an online booking is one) re-runs it, and so
do a booking made on the page and Customers' merge and erasure (the names it shows). The settings follow
this app's and the diary's (its booking rules). The public reads are asked by the page when it needs them.
"""

from live.live_registry import live

from apps.appointment.events import APPOINTMENT_EVENTS
from apps.appointment.events import SETTINGS_UPDATED as RULES_UPDATED
from apps.online_booking.events import BOOKING_CREATED, SETTINGS_UPDATED

#: A card merged or erased changes whose bookings these are, or the names they show.
CUSTOMER_GONE = ["customer.customer.merged", "customer.customer.erased"]
INBOX = [*APPOINTMENT_EVENTS, *CUSTOMER_GONE, BOOKING_CREATED]

live("online_booking.booking.list", on=INBOX)
live("online_booking.booking.get", on=INBOX)
live("online_booking.settings.get", on=[SETTINGS_UPDATED, RULES_UPDATED])
