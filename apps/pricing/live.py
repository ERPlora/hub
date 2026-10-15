"""Live queries of the pricing app and the events that re-run them after the COMMIT.

The price of a line (``pricing.price.resolve``) is asked for, not followed: it changes with the moment.
"""

from live.live_registry import live

from apps.pricing.events import (
    CATEGORY_DELETED,
    CATEGORY_UPDATED,
    GROUP_DELETED,
    GROUP_UPDATED,
    PRICE_ITEM_ADDED,
    PRICE_ITEM_EVENTS,
    PRICE_ITEM_REMOVED,
    PRICE_LIST_EVENTS,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    RULE_EVENTS,
)

GROUP = [GROUP_UPDATED, GROUP_DELETED]
PRODUCT = [PRODUCT_UPDATED, PRODUCT_DELETED]
CATEGORY = [CATEGORY_UPDATED, CATEGORY_DELETED]

# A list row names its group and counts its live prices (a deleted product's no longer count).
LIST_ROW = [*PRICE_LIST_EVENTS, PRICE_ITEM_ADDED, PRICE_ITEM_REMOVED, *GROUP, PRODUCT_DELETED]
live("pricing.price_list.list", on=LIST_ROW)
live("pricing.price_list.get", on=LIST_ROW)
# A price row shows its list's code and its product's name, SKU, unit and catalog price.
live("pricing.price_item.list", on=[*PRICE_ITEM_EVENTS, *PRICE_LIST_EVENTS, *PRODUCT])
# A rule row names its category, product and group.
live("pricing.rule.list", on=[*RULE_EVENTS, *PRODUCT, *CATEGORY, *GROUP])
