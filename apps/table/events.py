"""Events of the table app (``table.<entity>.<fact>``) and its reactions to Sales' and Customers' events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids and numbers, never a name or a free note (WORKBOOK «Lo que avisa»).

Reactions, each through an operation of this app run as the system, in its own transaction:

- a check of Sales charged in full (``sale.order.completed``) or voided (``sale.order.voided``) closes the
  table checks that hold it (TABLE-F18, F20);
- a customer's card erased (``customer.customer.erased``) leaves her holds without her name (F31).

Reservations is no reaction: it holds, moves and releases its table by calling ``table.hold.sync_reservation``,
``table.hold.move_reservation`` and ``table.hold.release`` inside its own transaction (F25–F28). Its events,
delivered afterwards, would replay the reservation as it was (an old «confirmed» would hold again the table of
a party already seated), so they are not listened to.

The outbox relay (``base.relay``, run by the worker on every tick) hands each event to ``react``; every
reaction is idempotent, so a repeated delivery changes nothing. What Sales did is also read on every read and
settled on every write (queries.py, services.py).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

ZONE_CREATED = "table.zone.created"
ZONE_UPDATED = "table.zone.updated"
ZONE_DELETED = "table.zone.deleted"
TABLE_CREATED = "table.table.created"
TABLE_UPDATED = "table.table.updated"
TABLE_DELETED = "table.table.deleted"
TABLE_HELD = "table.table.held"
TABLE_HOLD_RELEASED = "table.table.hold_released"
SESSION_OPENED = "table.session.opened"
SESSION_CLOSED = "table.session.closed"
SESSION_TRANSFERRED = "table.session.transferred"
SESSION_MERGED = "table.session.merged"
SESSION_SPLIT = "table.session.split"
SESSION_UPDATED = "table.session.updated"
SESSION_PARKED = "table.session.parked"
SESSION_RESTORED = "table.session.restored"
SESSION_DELETED = "table.session.deleted"
SETTINGS_UPDATED = "table.settings.updated"

ALL = [
    ZONE_CREATED,
    ZONE_UPDATED,
    ZONE_DELETED,
    TABLE_CREATED,
    TABLE_UPDATED,
    TABLE_DELETED,
    TABLE_HELD,
    TABLE_HOLD_RELEASED,
    SESSION_OPENED,
    SESSION_CLOSED,
    SESSION_TRANSFERRED,
    SESSION_MERGED,
    SESSION_SPLIT,
    SESSION_UPDATED,
    SESSION_PARKED,
    SESSION_RESTORED,
    SESSION_DELETED,
    SETTINGS_UPDATED,
]

ZONE_EVENTS = [ZONE_CREATED, ZONE_UPDATED, ZONE_DELETED]
TABLE_EVENTS = [TABLE_CREATED, TABLE_UPDATED, TABLE_DELETED]
HOLD_EVENTS = [TABLE_HELD, TABLE_HOLD_RELEASED]
#: Everything that changes who sits where (a table's status, its guests, its checks).
SESSION_EVENTS = [
    SESSION_OPENED,
    SESSION_CLOSED,
    SESSION_TRANSFERRED,
    SESSION_MERGED,
    SESSION_SPLIT,
    SESSION_UPDATED,
    SESSION_PARKED,
    SESSION_RESTORED,
    SESSION_DELETED,
]

# Other apps' events (their WORKBOOKs fix the payloads).
SALE_ORDER_COMPLETED = "sale.order.completed"
SALE_ORDER_VOIDED = "sale.order.voided"
#: What Sales does that frees a table or changes what a check charged: re-read on the live plan.
SALE_EVENTS = [
    SALE_ORDER_COMPLETED,
    SALE_ORDER_VOIDED,
    "sale.order.merged",
    "sale.sale.completed",
    "sale.sale.voided",
]
CUSTOMER_ERASED = "customer.customer.erased"
#: A check paints its customer's name (a card deleted, merged or erased no longer shows).
CUSTOMER_EVENTS = [
    "customer.order.linked",
    "customer.order.unlinked",
    "customer.customer.updated",
    CUSTOMER_ERASED,
    "customer.customer.deleted",
    "customer.customer.merged",
]

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    SALE_ORDER_COMPLETED: "table.session.close_by_order",
    SALE_ORDER_VOIDED: "table.session.close_by_order",
    CUSTOMER_ERASED: "table.hold.forget_customer",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
