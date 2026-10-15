"""Events of the online booking app (``online_booking.<entity>.<fact>``) and its reaction to Customers' erasure.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run each
live query. They carry ids, the number and the time, never the customer's note. A booking's later life
(confirmed, cancelled, completed, no-show, deleted) is announced by Citas: it happens to the appointment.

Reaction (WORKBOOK «A qué reacciona»): an erased card revokes the customer's links and forgets the device she
booked with (``customer.customer.erased``), through this app's own operation run as the system, in its own
transaction. Merging two cards needs nothing here: Citas moves the appointments and this app keeps no card.
The outbox relay (phase 2, in the worker) hands each delivered event to ``react``; the reaction is
idempotent, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

BOOKING_CREATED = "online_booking.booking.created"
SETTINGS_UPDATED = "online_booking.settings.updated"
ALL = [BOOKING_CREATED, SETTINGS_UPDATED]

# Other apps' events (their WORKBOOKs fix the payloads).
CUSTOMER_ERASED = "customer.customer.erased"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {CUSTOMER_ERASED: "online_booking.customer.erase"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
