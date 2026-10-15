"""Live queries of the combo app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.combo.events import (
    COMBO_CREATED,
    COMBO_DELETED,
    COMBO_UPDATED,
    GROUP_CREATED,
    GROUP_DELETED,
    GROUP_REORDERED,
    GROUP_UPDATED,
    OPTION_CREATED,
    OPTION_DELETED,
    OPTION_REORDERED,
    OPTION_UPDATED,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
)

MENU = [COMBO_CREATED, COMBO_UPDATED, COMBO_DELETED]
# A menu's tree: its courses and choices, and the product each choice shows (name, price, state).
TREE = [
    *MENU,
    GROUP_CREATED,
    GROUP_UPDATED,
    GROUP_DELETED,
    GROUP_REORDERED,
    OPTION_CREATED,
    OPTION_UPDATED,
    OPTION_DELETED,
    OPTION_REORDERED,
    PRODUCT_UPDATED,
    PRODUCT_DELETED,
]

# A row of the list counts the courses of its menu.
live("combo.combo.list", on=[*MENU, GROUP_CREATED, GROUP_DELETED])
live("combo.combo.get", on=TREE)
live("combo.combo.for_sale", on=TREE)
