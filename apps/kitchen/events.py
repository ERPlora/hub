"""Events of the kitchen app (``kitchen.<entity>.<fact>``) and its reactions to Sales' events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids, numbers and a reason, never a person's name (WORKBOOK «Lo que avisa»).

Reactions, each through an operation of this app run as the system, in its own transaction:

- a round fired (``sale.order.fired``) opens its ticket with what only the send knows (priority,
  channel, who sent it) and prints it (KITCHEN-F05, F08);
- a check charged in full, voided, or one of its lines voided (``sale.order.completed``,
  ``sale.order.voided``, ``sale.order.line_voided``) brings its tickets up to date (KITCHEN-F27 to F29).

The outbox relay (phase 2, in the worker) hands each delivered event to ``react``; every reaction is
idempotent, so a repeated delivery changes nothing. Until then, what Sales did is read on every read and
saved on every write (queries.py, services.py).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

TICKET_RECEIVED = "kitchen.ticket.received"
TICKET_CREATED = "kitchen.ticket.created"
TICKET_STARTED = "kitchen.ticket.started"
TICKET_READY = "kitchen.ticket.ready"
TICKET_SERVED = "kitchen.ticket.served"
TICKET_RECALLED = "kitchen.ticket.recalled"
TICKET_CANCELLED = "kitchen.ticket.cancelled"
TICKET_DELETED = "kitchen.ticket.deleted"
TICKET_UPDATED = "kitchen.ticket.updated"
TICKET_REPRINTED = "kitchen.ticket.reprinted"
ITEM_BUMPED = "kitchen.item.bumped"
ITEM_RECALLED = "kitchen.item.recalled"
ITEM_VOIDED = "kitchen.item.voided"
STATION_CREATED = "kitchen.station.created"
STATION_UPDATED = "kitchen.station.updated"
STATION_DELETED = "kitchen.station.deleted"
ROUTING_CHANGED = "kitchen.routing.changed"
SETTINGS_UPDATED = "kitchen.settings.updated"

ALL = [
    TICKET_RECEIVED,
    TICKET_CREATED,
    TICKET_STARTED,
    TICKET_READY,
    TICKET_SERVED,
    TICKET_RECALLED,
    TICKET_CANCELLED,
    TICKET_DELETED,
    TICKET_UPDATED,
    TICKET_REPRINTED,
    ITEM_BUMPED,
    ITEM_RECALLED,
    ITEM_VOIDED,
    STATION_CREATED,
    STATION_UPDATED,
    STATION_DELETED,
    ROUTING_CHANGED,
    SETTINGS_UPDATED,
]

#: Everything that changes a ticket or its dishes.
TICKET_EVENTS = [
    name for name in ALL if name.startswith(("kitchen.ticket.", "kitchen.item."))
]
STATION_EVENTS = [STATION_CREATED, STATION_UPDATED, STATION_DELETED]

# Sales' events (its WORKBOOK fixes the payloads).
SALE_ORDER_FIRED = "sale.order.fired"
SALE_ORDER_COMPLETED = "sale.order.completed"
SALE_ORDER_VOIDED = "sale.order.voided"
SALE_ORDER_LINE_VOIDED = "sale.order.line_voided"
#: What Sales does that changes the board: a round fired, a check charged, voided or merged, a line voided.
#: A line added or a check retitled in any till does not re-run every display (Sales has no event of its
#: own for a new title yet: asked to Sales, WORKBOOK «Lo que pide a otras apps»).
SALE_EVENTS = [
    SALE_ORDER_FIRED,
    SALE_ORDER_COMPLETED,
    SALE_ORDER_VOIDED,
    SALE_ORDER_LINE_VOIDED,
    "sale.order.merged",
]
#: A split moves lines to a new check (opened) and changes the old one: only a check's own tickets care.
SALE_CHECK_MOVES = ["sale.order.opened", "sale.order.changed"]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    SALE_ORDER_FIRED: "kitchen.ticket.receive",
    SALE_ORDER_COMPLETED: "kitchen.ticket.sync",
    SALE_ORDER_VOIDED: "kitchen.ticket.sync",
    SALE_ORDER_LINE_VOIDED: "kitchen.ticket.sync",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
