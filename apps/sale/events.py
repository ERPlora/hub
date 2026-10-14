"""Events of the sale app (``sale.<entity>.<fact>``) and its reaction to Customers' merge.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. ``sale.sale.completed`` and ``sale.sale.voided`` carry what Inventory
(``inventory.stock.apply_sale`` / ``restore_sale``) and Customers (``customer.purchase.record`` /
``void``) read from them (WORKBOOK «Lo que avisa»).

Reactions: two customer cards merged move the absorbed card's sales to the one that stays, through an
operation of this app run as the system, in its own transaction. The outbox relay (phase 2, in the
worker) hands each delivered event to ``react``; the operation is idempotent.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

SALE_COMPLETED = "sale.sale.completed"
SALE_CREATED_FROM_APPOINTMENT = "sale.sale.created_from_appointment"
SALE_VOIDED = "sale.sale.voided"
SALE_REFUNDED = "sale.sale.refunded"
SALE_REASSIGNED = "sale.sale.reassigned"
ORDER_OPENED = "sale.order.opened"
ORDER_CHANGED = "sale.order.changed"
ORDER_FIRED = "sale.order.fired"
ORDER_COMPLETED = "sale.order.completed"
ORDER_VOIDED = "sale.order.voided"
ORDER_MERGED = "sale.order.merged"
ORDER_LINE_REMOVED = "sale.order.line_removed"
ORDER_LINE_VOIDED = "sale.order.line_voided"
PAYMENT_METHOD_CREATED = "sale.payment_method.created"
SETTINGS_UPDATED = "sale.settings.updated"
DEPARTMENT_CREATED = "sale.department.created"
DEPARTMENT_UPDATED = "sale.department.updated"
DEPARTMENT_DELETED = "sale.department.deleted"
QUICK_NOTE_CREATED = "sale.quick_note.created"
QUICK_NOTE_UPDATED = "sale.quick_note.updated"
QUICK_NOTE_DELETED = "sale.quick_note.deleted"

ALL = [
    SALE_COMPLETED,
    SALE_CREATED_FROM_APPOINTMENT,
    SALE_VOIDED,
    SALE_REFUNDED,
    SALE_REASSIGNED,
    ORDER_OPENED,
    ORDER_CHANGED,
    ORDER_FIRED,
    ORDER_COMPLETED,
    ORDER_VOIDED,
    ORDER_MERGED,
    ORDER_LINE_REMOVED,
    ORDER_LINE_VOIDED,
    PAYMENT_METHOD_CREATED,
    SETTINGS_UPDATED,
    DEPARTMENT_CREATED,
    DEPARTMENT_UPDATED,
    DEPARTMENT_DELETED,
    QUICK_NOTE_CREATED,
    QUICK_NOTE_UPDATED,
    QUICK_NOTE_DELETED,
]

#: The events that change what a sale says (lists, figures, documents).
SALE_EVENTS = [SALE_COMPLETED, SALE_VOIDED, SALE_REFUNDED, SALE_REASSIGNED]
#: The events that change what an open check says.
ORDER_EVENTS = [
    ORDER_OPENED,
    ORDER_CHANGED,
    ORDER_FIRED,
    ORDER_COMPLETED,
    ORDER_VOIDED,
    ORDER_MERGED,
    ORDER_LINE_REMOVED,
    ORDER_LINE_VOIDED,
    SALE_COMPLETED,
]

# Customers' event (its WORKBOOK fixes the payload: ``{"id": survivor, "absorbed_id": absorbed}``).
CUSTOMER_MERGED = "customer.customer.merged"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {CUSTOMER_MERGED: "sale.customer.reassign"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
