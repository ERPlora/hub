"""Live queries of the inventory app and the events that re-run them after the COMMIT.

The units never change and the exports are files: they are not followed live.
"""

from live.live_registry import live

from apps.inventory.events import (
    CATEGORY_CREATED,
    CATEGORY_DELETED,
    CATEGORY_UPDATED,
    CONFIG_UPDATED,
    FIGURE_EVENTS,
    PRODUCT_CATEGORIZED,
    PRODUCT_DELETED,
    PRODUCT_EVENTS,
    PRODUCT_UNCATEGORIZED,
    PRODUCT_UPDATED,
    STOCK_CHANGED,
)

PRODUCT = PRODUCT_EVENTS
LINKS = [PRODUCT_CATEGORIZED, PRODUCT_UNCATEGORIZED]

# The settings decide which articles track stock, which every product list and the panel show.
live("inventory.product.list", on=[*PRODUCT, *LINKS, STOCK_CHANGED, CONFIG_UPDATED])
# A new product changes no existing detail.
live("inventory.product.get", on=[PRODUCT_UPDATED, PRODUCT_DELETED, *LINKS, STOCK_CHANGED, CONFIG_UPDATED])
# The sale catalog carries no stock: a movement does not re-run it.
live("inventory.product.list_for_sale", on=[*PRODUCT, CONFIG_UPDATED])
# The Home's panels follow the same events (apps.py).
live("inventory.product.list_low_stock", on=FIGURE_EVENTS)
# Only active products are mapped; deleting a category unlinks its products (and says so) first.
live("inventory.product_category.list", on=[*LINKS, PRODUCT_UPDATED, PRODUCT_DELETED, CATEGORY_DELETED])
# Each category counts its active products.
live(
    "inventory.category.list",
    on=[CATEGORY_CREATED, CATEGORY_UPDATED, CATEGORY_DELETED, *LINKS, PRODUCT_UPDATED, PRODUCT_DELETED],
)
# A movement shows its product's name and SKU.
live("inventory.movement.list", on=[STOCK_CHANGED, PRODUCT_UPDATED])
live("inventory.stock.get_summary", on=FIGURE_EVENTS)
live("inventory.config.get", on=[CONFIG_UPDATED])
