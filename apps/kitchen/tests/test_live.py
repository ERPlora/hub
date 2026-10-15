"""Live queries of the kitchen app: which events re-run which query after the COMMIT.

The board is live (KITCHEN-F10): every write of the kitchen, a station renamed or recoloured, the
routing (rounds not saved yet follow it), the settings («works from the screen» changes what charging
serves) and what Sales does to its checks (phase 1 has no relay: the read itself sees it) re-run it.
A line added or a check retitled in any till does not re-run the board (its cost per display); only the
tickets of one check follow its moves (a split).
"""

from live.live_registry import live_registry

from apps.kitchen import events

SALE = [
    "sale.order.fired",
    "sale.order.completed",
    "sale.order.voided",
    "sale.order.line_voided",
    "sale.order.merged",
]
#: A split moves lines to a new check (opened) and changes the old one: only a check's own tickets care.
CHECK_MOVES = ["sale.order.opened", "sale.order.changed"]
CATALOGUE = [
    "inventory.product.updated",
    "inventory.product.deleted",
    "inventory.category.updated",
    "inventory.category.deleted",
]
BOARD = [
    *events.TICKET_EVENTS,
    *events.STATION_EVENTS,
    events.ROUTING_CHANGED,
    events.SETTINGS_UPDATED,
    *SALE,
]


def kitchen_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("kitchen.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert kitchen_queries() == {
        "kitchen.ticket.board": BOARD,
        "kitchen.ticket.all_day": BOARD,
        "kitchen.ticket.list": BOARD,
        "kitchen.ticket.get": BOARD,
        "kitchen.ticket.by_order": [*BOARD, *CHECK_MOVES],
        "kitchen.station.list": BOARD,
        "kitchen.routing.list": [
            *events.STATION_EVENTS,
            events.ROUTING_CHANGED,
            *CATALOGUE,
        ],
        "kitchen.settings.get": [events.SETTINGS_UPDATED],
        "kitchen.log.list": [*events.TICKET_EVENTS, *events.STATION_EVENTS],
    }


def test_the_ticket_events_are_every_ticket_and_dish_event():
    assert events.TICKET_EVENTS == [
        "kitchen.ticket.received",
        "kitchen.ticket.created",
        "kitchen.ticket.started",
        "kitchen.ticket.ready",
        "kitchen.ticket.served",
        "kitchen.ticket.recalled",
        "kitchen.ticket.cancelled",
        "kitchen.ticket.deleted",
        "kitchen.ticket.updated",
        "kitchen.ticket.reprinted",
        "kitchen.item.bumped",
        "kitchen.item.recalled",
        "kitchen.item.voided",
    ]
