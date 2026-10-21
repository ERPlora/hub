"""Events of the combo app (``combo.<entity>.<fact>``) and its reaction to Inventory's.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. They carry ids (and a menu's name), never what a customer picked.

Reaction: a product deleted from Inventory leaves every menu (COMBO-F13), through an operation of this
app run as the system, in its own transaction. The worker's outbox relay (``base/relay.py``, every tick)
hands each delivered event to ``react``; the operation is idempotent, so a repeated delivery changes
nothing. Until the tick, and always, a choice whose product is deactivated or deleted is not offered nor
charged (``queries.offer_status``).
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

COMBO_CREATED = "combo.combo.created"
COMBO_UPDATED = "combo.combo.updated"
COMBO_DELETED = "combo.combo.deleted"
GROUP_CREATED = "combo.group.created"
GROUP_UPDATED = "combo.group.updated"
GROUP_DELETED = "combo.group.deleted"
GROUP_REORDERED = "combo.group.reordered"
OPTION_CREATED = "combo.option.created"
OPTION_UPDATED = "combo.option.updated"
OPTION_DELETED = "combo.option.deleted"
OPTION_REORDERED = "combo.option.reordered"

ALL = [
    COMBO_CREATED,
    COMBO_UPDATED,
    COMBO_DELETED,
    GROUP_CREATED,
    GROUP_UPDATED,
    GROUP_DELETED,
    GROUP_REORDERED,
    OPTION_CREATED,
    OPTION_UPDATED,
    OPTION_DELETED,
    OPTION_REORDERED,
]

# Inventory's events (its WORKBOOK fixes the payload): a product's name, price or state is what a
# choice shows, so they re-run the menus live; a deleted one also leaves every menu.
PRODUCT_UPDATED = "inventory.product.updated"
PRODUCT_DELETED = "inventory.product.deleted"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {PRODUCT_DELETED: "combo.option.drop_product"}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
