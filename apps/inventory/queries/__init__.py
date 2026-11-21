"""Read operations of the inventory app (``READ ONLY``): lists, the product, the sale catalog, the panel and exports.

Every list pages (``limit`` ≤ 100) with ``id`` as the tie-break, so pages never overlap, and has a
``search``. Deleted products and categories are out of every list; the ledger keeps showing their
movements. ``reads.find_product`` and ``reads.find_category`` resolve how a person names them (assistant, voice).
"""

from . import (
    categories as categories,
    exports as exports,
    movements as movements,
    products as products,
    reads as reads,
    recovery as recovery,
    settings as settings,
    stock as stock,
    units as units,
)
