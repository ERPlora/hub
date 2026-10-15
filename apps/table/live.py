"""Live queries of the table app and the events that re-run them after the COMMIT.

The floor is live (TABLE-F09): a table's status is computed when read from its checks, its block and
its holds, so everything that changes one of them re-runs the plan — this app's own writes, Sales
charging or voiding a table's check (phase 1 has no relay: the read itself sees what Sales did) and
Customers putting a card on a check or erasing it.
"""

from live.live_registry import live

from apps.table.events import (
    CUSTOMER_EVENTS,
    HOLD_EVENTS,
    SALE_EVENTS,
    SESSION_DELETED,
    SESSION_EVENTS,
    SESSION_OPENED,
    SETTINGS_UPDATED,
    TABLE_EVENTS,
    ZONE_EVENTS,
)

#: Every table of the plan: its box, its zone, its status (checks, block, holds), its customer.
FLOOR = [
    *TABLE_EVENTS,
    *ZONE_EVENTS,
    *HOLD_EVENTS,
    *SESSION_EVENTS,
    *SALE_EVENTS,
    *CUSTOMER_EVENTS,
]
#: The checks of the room: their table and zone, their status and what Sales charged, their customer.
CHECKS = [*SESSION_EVENTS, *TABLE_EVENTS, *ZONE_EVENTS, *SALE_EVENTS, *CUSTOMER_EVENTS]
#: A zone counts its tables and the free ones.
ZONES = [*ZONE_EVENTS, *TABLE_EVENTS, *HOLD_EVENTS, *SESSION_EVENTS, *SALE_EVENTS]

live("table.zone.list", on=ZONES)
live("table.zone.get", on=ZONES)
live("table.table.list", on=FLOOR)
live("table.table.get", on=FLOOR)
live("table.session.list", on=CHECKS)
live("table.session.get", on=CHECKS)
live("table.session.by_order", on=CHECKS)
live("table.waiter.list", on=[SESSION_OPENED, SESSION_DELETED])
live("table.floor.status", on=[*TABLE_EVENTS, *ZONE_EVENTS])
live("table.settings.get", on=[SETTINGS_UPDATED])
