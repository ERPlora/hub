"""Events of the inventory app (``inventory.<entity>.<fact>``) and its reactions to the Sales app's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that
re-run each live query. Each event carries only what the WORKBOOK's «Lo que avisa» lists.

Reactions: a paid sale lowers the stock, a voided one restores it and a refund puts its returned units
back, each through an operation of this app run as the system, in its own transaction. The worker's outbox
relay (``base/relay.py``) hands each delivered event to ``react``; the operations are idempotent per sale
(per refund for a refund), so a repeated delivery changes nothing. ``sale`` does not require ``inventory`` (PLAN §20.5): this is the only link.
"""

from typing import Any

from live.context import Scope, system_context
from live.operations import get

PRODUCT_CREATED = "inventory.product.created"
PRODUCT_UPDATED = "inventory.product.updated"
PRODUCT_DELETED = "inventory.product.deleted"
PRODUCT_CATEGORIZED = "inventory.product.categorized"
PRODUCT_UNCATEGORIZED = "inventory.product.uncategorized"
# Not in the WORKBOOK's list: they only re-run the category lists of the screens (live.py).
CATEGORY_CREATED = "inventory.category.created"
CATEGORY_UPDATED = "inventory.category.updated"
CATEGORY_DELETED = "inventory.category.deleted"
STOCK_CHANGED = "inventory.stock.changed"
STOCK_THRESHOLD_CROSSED = "inventory.stock.threshold_crossed"
# Not in the WORKBOOK's list either: the settings decide what the panel counts, so it re-runs it.
CONFIG_UPDATED = "inventory.config.updated"

ALL = [
    PRODUCT_CREATED,
    PRODUCT_UPDATED,
    PRODUCT_DELETED,
    PRODUCT_CATEGORIZED,
    PRODUCT_UNCATEGORIZED,
    CATEGORY_CREATED,
    CATEGORY_UPDATED,
    CATEGORY_DELETED,
    STOCK_CHANGED,
    STOCK_THRESHOLD_CROSSED,
    CONFIG_UPDATED,
]

#: A product added, changed or deleted: what may change how many active products there are («Your catalog»).
PRODUCT_EVENTS = [PRODUCT_CREATED, PRODUCT_UPDATED, PRODUCT_DELETED]
#: What re-runs the Panel's figures and its low-stock list, and with them the Home's panels: the settings decide which
#: articles track stock.
FIGURE_EVENTS = [*PRODUCT_EVENTS, STOCK_CHANGED, CONFIG_UPDATED]

# The Sales app's events (its WORKBOOK fixes their payload).
SALE_COMPLETED = "sale.sale.completed"
SALE_VOIDED = "sale.sale.voided"
# INVENTORY-F24 (2026-10-14): the units a refund returns go back to the stock.
SALE_REFUNDED = "sale.sale.refunded"

#: Event of another app → the operation of this app that reacts to it.
REACTIONS = {
    SALE_COMPLETED: "inventory.stock.apply_sale",
    SALE_VOIDED: "inventory.stock.restore_sale",
    SALE_REFUNDED: "inventory.stock.restore_refund",
}


def react(scope: Scope, name: str, payload: dict[str, Any]):
    """Run this app's reaction to the event ``name`` of ``scope`` as the system; ``None`` if it has none."""
    operation_name = REACTIONS.get(name)
    if operation_name is None:
        return None
    reaction = get(operation_name)
    return reaction(system_context(scope), reaction.input.model_validate(payload))
