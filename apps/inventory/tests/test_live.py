"""Live queries of the inventory app: which events re-run which query after the COMMIT."""

from pathlib import Path

from live.live_registry import live_registry
from live.operations import get

from apps.inventory import events

EVENTS_SOURCE = Path(events.__file__).read_text()
PRODUCT = [events.PRODUCT_CREATED, events.PRODUCT_UPDATED, events.PRODUCT_DELETED]
LINKS = [events.PRODUCT_CATEGORIZED, events.PRODUCT_UNCATEGORIZED]


def inventory_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("inventory.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert inventory_queries() == {
        "inventory.product.list": [*PRODUCT, *LINKS, events.STOCK_CHANGED, events.CONFIG_UPDATED],
        # A new product changes no existing detail.
        "inventory.product.get": [events.PRODUCT_UPDATED, events.PRODUCT_DELETED, *LINKS, events.STOCK_CHANGED, events.CONFIG_UPDATED],
        # The sale catalog carries no stock: a movement does not re-run it.
        "inventory.product.list_for_sale": [*PRODUCT, events.CONFIG_UPDATED],
        "inventory.product.list_low_stock": [*PRODUCT, events.STOCK_CHANGED, events.CONFIG_UPDATED],
        "inventory.product_category.list": [*LINKS, events.PRODUCT_UPDATED, events.PRODUCT_DELETED, events.CATEGORY_DELETED],
        "inventory.category.list": [
            events.CATEGORY_CREATED,
            events.CATEGORY_UPDATED,
            events.CATEGORY_DELETED,
            *LINKS,
            events.PRODUCT_UPDATED,
            events.PRODUCT_DELETED,
        ],
        "inventory.movement.list": [events.STOCK_CHANGED, events.PRODUCT_UPDATED],
        "inventory.stock.get_summary": [*PRODUCT, events.STOCK_CHANGED, events.CONFIG_UPDATED],
        "inventory.config.get": [events.CONFIG_UPDATED],
    }


def test_every_live_query_is_a_read_with_a_permission():
    for name in inventory_queries():
        op = get(name)
        assert (op.kind, op.permission is not None) == ("query", True), name


def test_every_event_is_a_literal_of_events_py():
    for on in inventory_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_stock_movement_re_runs_the_panel_the_low_stock_the_list_and_the_ledger():
    assert live_registry.affected([events.STOCK_CHANGED]) >= {
        "inventory.stock.get_summary",
        "inventory.product.list_low_stock",
        "inventory.product.list",
        "inventory.product.get",
        "inventory.movement.list",
    }
    assert "inventory.product.list_for_sale" not in live_registry.affected([events.STOCK_CHANGED])
