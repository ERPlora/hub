"""Events of the cash register app (``cash_register.<entity>.<fact>``) and its reactions: none.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. Each event carries only what the WORKBOOK's «Lo que avisa» lists.

No reactions: the sale lines of a shift are read from sale (its requirement) when they are looked at, so
a charge, a void or a refund is in the open shift at once, without the outbox relay of phase 2, and none
is lost if an event never arrives. Sale's events only re-run the drawer's live queries (``SALE_EVENTS``).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

SETTINGS_UPDATED = "cash_register.settings.updated"
REGISTER_CREATED = "cash_register.register.created"
REGISTER_UPDATED = "cash_register.register.updated"
SESSION_OPENED = "cash_register.session.opened"
SESSION_CLOSED = "cash_register.session.closed"
MOVEMENT_ADDED = "cash_register.movement.added"
COUNT_ADDED = "cash_register.count.added"

ALL = [
    SETTINGS_UPDATED,
    REGISTER_CREATED,
    REGISTER_UPDATED,
    SESSION_OPENED,
    SESSION_CLOSED,
    MOVEMENT_ADDED,
    COUNT_ADDED,
]

# The Sales app's events (its WORKBOOK fixes them): a charge, a void and a refund change the open shift.
SALE_COMPLETED = "sale.sale.completed"
SALE_VOIDED = "sale.sale.voided"
SALE_REFUNDED = "sale.sale.refunded"
SALE_EVENTS = [SALE_COMPLETED, SALE_VOIDED, SALE_REFUNDED]

#: Event of another app → the operation of this app that reacts to it: none (see above).
REACTIONS: dict[str, str] = {}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope``; ``None``: it reacts to none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
