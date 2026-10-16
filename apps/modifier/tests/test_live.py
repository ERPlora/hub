"""Live queries of the modifier app: which events re-run which read."""

from pathlib import Path

from live.live_registry import live_registry

from apps.modifier import events

EVENTS_SOURCE = Path(events.__file__).read_text()
GROUP = ["modifier.group.created", "modifier.group.updated", "modifier.group.deleted"]
OPTION = [
    "modifier.option.created",
    "modifier.option.updated",
    "modifier.option.deleted",
]
LINK = ["modifier.link.attached", "modifier.link.detached"]
# What Inventory says that changes what a link names or which groups a product carries.
INVENTORY_TARGET = [
    "inventory.product.updated",
    "inventory.product.deleted",
    "inventory.category.updated",
    "inventory.category.deleted",
]
INVENTORY_MEMBERSHIP = [
    "inventory.product.categorized",
    "inventory.product.uncategorized",
]


def modifier_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("modifier.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_read_and_its_events():
    assert modifier_queries() == {
        # The counts of options and links are columns of the table; a deleted target stops counting.
        "modifier.group.list": [
            *GROUP,
            *OPTION,
            *LINK,
            "inventory.product.deleted",
            "inventory.category.deleted",
        ],
        "modifier.group.get": [
            *GROUP,
            *OPTION,
            *LINK,
            "inventory.product.deleted",
            "inventory.category.deleted",
        ],
        # An option shows its group's name.
        "modifier.option.list": [
            *OPTION,
            "modifier.group.updated",
            "modifier.group.deleted",
        ],
        "modifier.link.list": [
            *LINK,
            "modifier.group.updated",
            "modifier.group.deleted",
            *INVENTORY_TARGET,
        ],
        # What the till asks for a product: any change of the catalog or of the product's categories.
        "modifier.group.for_target": [
            *GROUP,
            *OPTION,
            *LINK,
            *INVENTORY_TARGET,
            *INVENTORY_MEMBERSHIP,
        ],
    }


def test_every_own_event_is_a_literal_of_events_py():
    for on in modifier_queries().values():
        for event in on:
            if event.startswith("modifier."):
                assert f'"{event}"' in EVENTS_SOURCE, event


def test_the_valuation_is_not_followed_live():
    # It is asked once, when the line is added, and must answer what the catalog says at that moment.
    assert "modifier.selection.resolve" not in modifier_queries()


def test_a_new_option_re_runs_the_screen_and_the_till_but_not_the_links():
    affected = live_registry.affected(["modifier.option.created"])
    assert {
        "modifier.group.list",
        "modifier.option.list",
        "modifier.group.for_target",
    } <= affected
    assert "modifier.link.list" not in affected
