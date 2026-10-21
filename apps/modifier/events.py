"""Events of the modifier app (``modifier.<entity>.<fact>``) and its reactions to Inventory's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. Each event carries only what the WORKBOOK's «Lo que avisa» lists.

Reactions (MODIFIER-F09): a product or a category deleted in Inventory drops the groups hung from it,
through an operation of this app run as the system, in its own transaction. The worker's outbox relay
(``base/relay.py``, every tick) hands each delivered event to ``react``; the operations are idempotent, so
a repeated delivery changes nothing. Until the tick, the reads leave out the links to what is deleted.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

GROUP_CREATED = "modifier.group.created"
GROUP_UPDATED = "modifier.group.updated"
GROUP_DELETED = "modifier.group.deleted"
OPTION_CREATED = "modifier.option.created"
OPTION_UPDATED = "modifier.option.updated"
OPTION_DELETED = "modifier.option.deleted"
LINK_ATTACHED = "modifier.link.attached"
LINK_DETACHED = "modifier.link.detached"

ALL = [
    GROUP_CREATED,
    GROUP_UPDATED,
    GROUP_DELETED,
    OPTION_CREATED,
    OPTION_UPDATED,
    OPTION_DELETED,
    LINK_ATTACHED,
    LINK_DETACHED,
]

GROUP_EVENTS = [GROUP_CREATED, GROUP_UPDATED, GROUP_DELETED]
OPTION_EVENTS = [OPTION_CREATED, OPTION_UPDATED, OPTION_DELETED]
LINK_EVENTS = [LINK_ATTACHED, LINK_DETACHED]

# Inventory's events (its WORKBOOK fixes their payload: the deleted row's ``id``).
PRODUCT_DELETED = "inventory.product.deleted"
CATEGORY_DELETED = "inventory.category.deleted"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    PRODUCT_DELETED: "modifier.link.drop_product",
    CATEGORY_DELETED: "modifier.link.drop_category",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
