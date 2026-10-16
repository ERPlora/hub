"""Live queries of the kitchen app and the events that re-run them after the COMMIT.

The board is live (KITCHEN-F10): every write of the kitchen, a station renamed or recoloured, the routing
(a round not saved yet follows it), the settings («works from the screen» changes what charging serves)
and what Sales does to its checks re-run it — phase 1 has no relay: the read itself sees what Sales did.
"""

from live.live_registry import live

from apps.kitchen.events import (
    ROUTING_CHANGED,
    SALE_CHECK_MOVES,
    SALE_EVENTS,
    SETTINGS_UPDATED,
    STATION_EVENTS,
    TICKET_EVENTS,
)

#: The names of the products and categories of the routing are Inventory's.
CATALOGUE = [
    "inventory.product.updated",
    "inventory.product.deleted",
    "inventory.category.updated",
    "inventory.category.deleted",
]
#: Everything a ticket shows: its state, its stations, the routing of a round not saved yet, the
#: settings and what Sales did.
BOARD = [
    *TICKET_EVENTS,
    *STATION_EVENTS,
    ROUTING_CHANGED,
    SETTINGS_UPDATED,
    *SALE_EVENTS,
]

live("kitchen.ticket.board", on=BOARD)
live("kitchen.ticket.all_day", on=BOARD)
live("kitchen.ticket.list", on=BOARD)
live("kitchen.ticket.get", on=BOARD)
live("kitchen.ticket.by_order", on=[*BOARD, *SALE_CHECK_MOVES])
live("kitchen.station.list", on=BOARD)
live("kitchen.routing.list", on=[*STATION_EVENTS, ROUTING_CHANGED, *CATALOGUE])
live("kitchen.settings.get", on=[SETTINGS_UPDATED])
live("kitchen.log.list", on=[*TICKET_EVENTS, *STATION_EVENTS])
