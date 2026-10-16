"""Live queries of the pricing app: which events re-run which query."""

from pathlib import Path

from live.live_registry import live_registry

from apps.pricing import events, services

EVENTS_SOURCE = Path(events.__file__).read_text()
SERVICES_SOURCE = Path(services.__file__).read_text()

LISTS = events.PRICE_LIST_EVENTS
ITEMS = events.PRICE_ITEM_EVENTS
RULES = events.RULE_EVENTS
GROUP = ["customer.group.updated", "customer.group.deleted"]
PRODUCT = ["inventory.product.updated", "inventory.product.deleted"]
CATEGORY = ["inventory.category.updated", "inventory.category.deleted"]


def pricing_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("pricing.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_every_list_query_can_be_followed_live_and_the_price_of_a_line_is_asked():
    assert set(pricing_queries()) == {
        "pricing.price_list.list",
        "pricing.price_list.get",
        "pricing.price_item.list",
        "pricing.rule.list",
    }


def test_each_query_and_its_events():
    queries = pricing_queries()
    # A list row names its group and counts its live prices.
    for name in ("pricing.price_list.list", "pricing.price_list.get"):
        assert queries[name] == [*LISTS, events.PRICE_ITEM_ADDED, events.PRICE_ITEM_REMOVED, *GROUP, "inventory.product.deleted"], name
    # A price row shows its list's code and its product's name, SKU, unit and catalog price.
    assert queries["pricing.price_item.list"] == [*ITEMS, *LISTS, *PRODUCT]
    # A rule row names its category, product and group.
    assert queries["pricing.rule.list"] == [*RULES, *PRODUCT, *CATEGORY, *GROUP]


def test_every_own_event_is_a_literal_of_events_py_recorded_by_a_service():
    for on in pricing_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event
    for name, value in vars(events).items():
        if name.isupper() and isinstance(value, str) and value.startswith("pricing."):
            assert f"events.{name}" in SERVICES_SOURCE, name


def test_a_rule_does_not_re_run_the_prices():
    affected = live_registry.affected([events.RULE_CREATED])
    assert "pricing.price_item.list" not in affected
    assert "pricing.rule.list" in affected
