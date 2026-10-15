"""Events of the customer app (``customer.<entity>.<fact>``) and its reactions to the Sales app's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids only, never personal data: whoever needs the card asks
``customer.customer.detail``.

Reactions (WORKBOOK «A qué reacciona»): a paid sale is recorded on its customer's card, a voided one
taken off and a refund subtracted from the spend, each through an operation of this app run as the
system, in its own transaction. The outbox relay (phase 2, in the worker) hands each delivered event
to ``react``; the operations are idempotent per sale and per refund, so a repeated delivery changes
nothing. ``customer`` does not require ``sale``: this is the only link.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

CUSTOMER_CREATED = "customer.customer.created"
CUSTOMER_UPDATED = "customer.customer.updated"
CUSTOMER_GROUPS_CHANGED = "customer.customer.groups_changed"
CUSTOMER_TAGS_CHANGED = "customer.customer.tags_changed"
CUSTOMER_DELETED = "customer.customer.deleted"
CUSTOMER_MERGED = "customer.customer.merged"
CUSTOMER_ERASED = "customer.customer.erased"
NOTE_ADDED = "customer.note.added"
ACTIVITY_RECORDED = "customer.activity.recorded"
CONSENT_GRANTED = "customer.consent.granted"
CONSENT_WITHDRAWN = "customer.consent.withdrawn"
ORDER_LINKED = "customer.order.linked"
ORDER_UNLINKED = "customer.order.unlinked"
PURCHASE_RECORDED = "customer.purchase.recorded"
PURCHASE_VOIDED = "customer.purchase.voided"
PURCHASE_REFUNDED = "customer.purchase.refunded"
GROUP_CREATED = "customer.group.created"
GROUP_UPDATED = "customer.group.updated"
GROUP_DELETED = "customer.group.deleted"
TAG_CREATED = "customer.tag.created"
TAG_UPDATED = "customer.tag.updated"
TAG_DELETED = "customer.tag.deleted"
FIELD_CREATED = "customer.field.created"
FIELD_UPDATED = "customer.field.updated"
FIELD_DELETED = "customer.field.deleted"

ALL = [
    CUSTOMER_CREATED,
    CUSTOMER_UPDATED,
    CUSTOMER_GROUPS_CHANGED,
    CUSTOMER_TAGS_CHANGED,
    CUSTOMER_DELETED,
    CUSTOMER_MERGED,
    CUSTOMER_ERASED,
    NOTE_ADDED,
    ACTIVITY_RECORDED,
    CONSENT_GRANTED,
    CONSENT_WITHDRAWN,
    ORDER_LINKED,
    ORDER_UNLINKED,
    PURCHASE_RECORDED,
    PURCHASE_VOIDED,
    PURCHASE_REFUNDED,
    GROUP_CREATED,
    GROUP_UPDATED,
    GROUP_DELETED,
    TAG_CREATED,
    TAG_UPDATED,
    TAG_DELETED,
    FIELD_CREATED,
    FIELD_UPDATED,
    FIELD_DELETED,
]

# The Sales app's events (its WORKBOOK fixes their payload).
SALE_COMPLETED = "sale.sale.completed"
SALE_VOIDED = "sale.sale.voided"
SALE_REFUNDED = "sale.sale.refunded"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    SALE_COMPLETED: "customer.purchase.record",
    SALE_VOIDED: "customer.purchase.void",
    SALE_REFUNDED: "customer.purchase.refund",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
