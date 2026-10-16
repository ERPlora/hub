"""Kitchen with the real Inventory (a ``requires``): its products and categories decide the station of a
dish (KITCHEN-F04), by their own operations, never by hand.

Cases from the old module's tests: stations.hub (routing by product, then by category), the routing panel
(products and categories by name), the dropdowns of the routing (Inventory's lists).
"""

import pytest
from live.context import system_context

from .conftest import A, add_line, fire, open_check, run

pytestmark = pytest.mark.django_db


def inventory(name: str, data: dict):
    return run(name, data, system_context(A))


def test_a_dish_goes_by_the_category_sales_froze_on_its_line_when_the_product_has_no_route(
    clock, product, category
):
    drinks, wines = category("Drinks"), category("Wines")
    run("kitchen.station.create", {"name": "Bar"})
    run("kitchen.station.create", {"name": "Cellar"})
    run("kitchen.routing.set", {"station": "Bar", "category": "Drinks"})
    run("kitchen.routing.set", {"station": "Cellar", "category": "Wines"})
    rioja = product("Rioja", category_ids=[str(wines.id), str(drinks.id)])
    order = open_check("Table 4")
    add_line(order.id, rioja)
    fire(order.id)
    [ticket] = run("kitchen.ticket.board", {}).cooking
    # Sales freezes the product's first category (Inventory's order, by name) on the line; the kitchen
    # routes by that one.
    assert ticket.items[0].station_name == "Bar"


def test_a_products_own_route_wins_over_its_category(clock, product, category):
    drinks = category("Drinks")
    run("kitchen.station.create", {"name": "Bar"})
    run("kitchen.station.create", {"name": "Grill"})
    run("kitchen.routing.set", {"station": "Bar", "category": "Drinks"})
    sangria = product("Hot sangria", category_ids=[str(drinks.id)])
    run("kitchen.routing.set", {"station": "Grill", "product": "hot sangria"})
    order = open_check("Table 4")
    add_line(order.id, sangria)
    fire(order.id)
    assert run("kitchen.ticket.board", {}).cooking[0].items[0].station_name == "Grill"


def test_the_routing_reads_inventorys_names_as_they_are_now(product, category):
    burger = product("Burger")
    run("kitchen.station.create", {"name": "Grill"})
    run("kitchen.routing.set", {"station": "Grill", "product_id": str(burger.id)})
    inventory(
        "inventory.product.update",
        {"id": str(burger.id), "name": "Smash burger"},
    )
    assert [row.target_name for row in run("kitchen.routing.list", {}).rows] == [
        "Smash burger"
    ]


def test_a_product_deleted_in_inventory_leaves_the_routing_and_frees_its_station(
    product,
):
    burger = product("Burger")
    run("kitchen.station.create", {"name": "Grill"})
    run("kitchen.routing.set", {"station": "Grill", "product": "Burger"})
    inventory("inventory.product.delete", {"id": str(burger.id)})
    assert run("kitchen.routing.list", {}).rows == []
    [station] = run("kitchen.station.list", {}).rows
    assert station.routes == 0
    assert run("kitchen.station.delete", {"station": "Grill"}).id == station.id


def test_a_ticket_by_hand_takes_the_catalogue_product_its_price_and_its_station(
    clock, product, category
):
    desserts = category("Desserts")
    run("kitchen.station.create", {"name": "Pastry"})
    run("kitchen.routing.set", {"station": "Pastry", "category": "Desserts"})
    product("Cheesecake", price=550, category_ids=[str(desserts.id)])
    ticket = run(
        "kitchen.ticket.create", {"items": [{"product": "cheese", "quantity": "2"}]}
    )
    [item] = ticket.items
    assert (item.name, item.station_name, ticket.total) == (
        "Cheesecake",
        "Pastry",
        1100,
    )


def test_a_category_deleted_in_inventory_is_no_longer_named_for_routing(category):
    drinks = category("Drinks")
    run("kitchen.station.create", {"name": "Bar"})
    inventory("inventory.category.delete", {"id": str(drinks.id)})
    from live.errors import NotFound

    with pytest.raises(NotFound) as refused:
        run("kitchen.routing.set", {"station": "Bar", "category": "Drinks"})
    assert refused.value.code == "kitchen.category_not_found"
