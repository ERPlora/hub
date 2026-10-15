"""Live queries of the modifier app and the events that re-run them after the COMMIT.

The valuation of a choice (``modifier.selection.resolve``) is not followed: Sales asks it once, when the
line is added, and freezes what it answers.
"""

from live.live_registry import live

from apps.modifier.events import (
    CATEGORY_DELETED,
    GROUP_DELETED,
    GROUP_EVENTS,
    GROUP_UPDATED,
    LINK_EVENTS,
    OPTION_EVENTS,
    PRODUCT_DELETED,
)

# Inventory's events that change what a link names, or which groups a product carries.
PRODUCT_UPDATED = "inventory.product.updated"
CATEGORY_UPDATED = "inventory.category.updated"
PRODUCT_CATEGORIZED = "inventory.product.categorized"
PRODUCT_UNCATEGORIZED = "inventory.product.uncategorized"
TARGET = [PRODUCT_UPDATED, PRODUCT_DELETED, CATEGORY_UPDATED, CATEGORY_DELETED]

# The counts of options and links are columns of the table; a deleted target stops counting.
CATALOG = [
    *GROUP_EVENTS,
    *OPTION_EVENTS,
    *LINK_EVENTS,
    PRODUCT_DELETED,
    CATEGORY_DELETED,
]
live("modifier.group.list", on=CATALOG)
live("modifier.group.get", on=CATALOG)
# An option shows its group's name.
live("modifier.option.list", on=[*OPTION_EVENTS, GROUP_UPDATED, GROUP_DELETED])
live("modifier.link.list", on=[*LINK_EVENTS, GROUP_UPDATED, GROUP_DELETED, *TARGET])
# What the till asks for a product: any change of the catalog or of the product's categories.
live(
    "modifier.group.for_target",
    on=[
        *GROUP_EVENTS,
        *OPTION_EVENTS,
        *LINK_EVENTS,
        *TARGET,
        PRODUCT_CATEGORIZED,
        PRODUCT_UNCATEGORIZED,
    ],
)
