"""Write operations of the inventory app: one operation = one transaction, with its events in the outbox.

Every change of stock goes through ``movements._move``: the product's row is locked, its balance and its
ledger movement are written together, and ``inventory.stock.changed`` is recorded. Several products are
locked in the order of their ids, so two writes never wait for each other in a circle. A quantity off
the step of its unit is refused, never rounded. Nothing is validated after something was written:
every check runs first, so a refusal leaves no trace.
"""

from . import (
    categories as categories,
    imports as imports,
    labels as labels,
    movements as movements,
    product_categories as product_categories,
    product_images as product_images,
    products as products,
    sale_reactions as sale_reactions,
    settings as settings,
    skus as skus,
    stock as stock,
    writes as writes,
)
