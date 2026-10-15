"""Events of the pricing app (``pricing.<entity>.<fact>``) and its reactions to other apps' events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids, codes, quantities and prices, never a customer.

Reactions: a product or a category Inventory deletes, a customer group Customers deletes, and a service
Services changes, each through an operation of this app run as the system, in its own transaction
(WORKBOOK PRICING-F14). The outbox relay (phase 2, in the worker) hands each delivered event to
``react``; the operations are idempotent, so a repeated delivery changes nothing.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

PRICE_LIST_CREATED = "pricing.price_list.created"
PRICE_LIST_UPDATED = "pricing.price_list.updated"
PRICE_LIST_DEFAULT_CHANGED = "pricing.price_list.default_changed"
PRICE_LIST_DEACTIVATED = "pricing.price_list.deactivated"
PRICE_LIST_ACTIVATED = "pricing.price_list.activated"
PRICE_ITEM_ADDED = "pricing.price_item.added"
PRICE_ITEM_UPDATED = "pricing.price_item.updated"
PRICE_ITEM_REMOVED = "pricing.price_item.removed"
RULE_CREATED = "pricing.rule.created"
RULE_UPDATED = "pricing.rule.updated"
RULE_DEACTIVATED = "pricing.rule.deactivated"
RULE_ACTIVATED = "pricing.rule.activated"

ALL = [
    PRICE_LIST_CREATED,
    PRICE_LIST_UPDATED,
    PRICE_LIST_DEFAULT_CHANGED,
    PRICE_LIST_DEACTIVATED,
    PRICE_LIST_ACTIVATED,
    PRICE_ITEM_ADDED,
    PRICE_ITEM_UPDATED,
    PRICE_ITEM_REMOVED,
    RULE_CREATED,
    RULE_UPDATED,
    RULE_DEACTIVATED,
    RULE_ACTIVATED,
]
PRICE_LIST_EVENTS = [
    PRICE_LIST_CREATED,
    PRICE_LIST_UPDATED,
    PRICE_LIST_DEFAULT_CHANGED,
    PRICE_LIST_DEACTIVATED,
    PRICE_LIST_ACTIVATED,
]
PRICE_ITEM_EVENTS = [PRICE_ITEM_ADDED, PRICE_ITEM_UPDATED, PRICE_ITEM_REMOVED]
RULE_EVENTS = [RULE_CREATED, RULE_UPDATED, RULE_DEACTIVATED, RULE_ACTIVATED]

# Other apps' events (their WORKBOOKs fix the payload: ``{"id": …}`` and more).
PRODUCT_UPDATED = "inventory.product.updated"
PRODUCT_DELETED = "inventory.product.deleted"
CATEGORY_UPDATED = "inventory.category.updated"
CATEGORY_DELETED = "inventory.category.deleted"
GROUP_UPDATED = "customer.group.updated"
GROUP_DELETED = "customer.group.deleted"
SERVICE_UPDATED = "service.service.updated"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    PRODUCT_DELETED: "pricing.catalog.forget_product",
    CATEGORY_DELETED: "pricing.catalog.forget_category",
    GROUP_DELETED: "pricing.catalog.forget_group",
    SERVICE_UPDATED: "pricing.catalog.refresh_service",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
