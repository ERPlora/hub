"""Live queries of the reservation app and the events that re-run them after the COMMIT.

The book is live: whatever changes a reservation re-runs the day's list, its figures and the occupancy of
its slots (``availability.day``, which also follows the slots, the blocked dates and the business's hours
in Schedules); a reservation row paints its table, so Tables renaming, moving or taking one out of service
re-runs the rows and the free tables. The waitlist, the slots, the blocked dates and the rules follow
their own events.
"""

from live.live_registry import live

from apps.reservation.events import (
    BLOCKED_EVENTS,
    RESERVATION_EVENTS,
    SCHEDULE_EVENTS,
    SETTINGS_UPDATED,
    SLOT_EVENTS,
    TABLE_EVENTS,
    WAITLIST_EVENTS,
)

#: A reservation row, with the label of its table.
BOOK = [*RESERVATION_EVENTS, *TABLE_EVENTS]
#: A day: its reservations and covers, its slots and what they hold, its blocks and its opening hours.
DAY = [*RESERVATION_EVENTS, *SLOT_EVENTS, *BLOCKED_EVENTS, *SCHEDULE_EVENTS]
#: The free tables: the reservations that hold them and the tables in service.
TABLES = [*RESERVATION_EVENTS, *TABLE_EVENTS]

live("reservation.reservation.list", on=BOOK)
live("reservation.reservation.get", on=BOOK)
live("reservation.availability.day", on=DAY)
live("reservation.availability.tables", on=TABLES)
live("reservation.time_slot.list", on=SLOT_EVENTS)
live("reservation.blocked_date.list", on=BLOCKED_EVENTS)
live("reservation.waitlist.list", on=WAITLIST_EVENTS)
live("reservation.settings.get", on=[SETTINGS_UPDATED])
