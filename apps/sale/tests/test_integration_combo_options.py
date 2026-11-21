"""Sale, Menus and Modifiers together, no mocks: the options of a dish picked in a menu (SALE-F42).

A dish of a menu asks the same groups of Modifiers it asks sold on its own. Sales has Modifiers check and value the
options of each dish (``modifier.selection.resolve``, with the seller's session) and hands them to Menus, which adds
them to the menu's amount and, to take away, splits them with its dishes. The line freezes them under their dish: the
kitchen reads them under the dish, the ticket names them with it, and the menu charges what it was ordered at even when
an option changes or goes away later. A required group left empty refuses the menu, also through the API.
"""

import pytest
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.sale.models import Order, SaleLine
from apps.sale.tests.conftest import HUB_DB, A, run

pytestmark = HUB_DB

#: Taxes' factory catalogue: restaurant food (10 %), a restaurant's alcohol (10 % at the table, 21 % to take away)
#: and the general rate (21 %).
FOOD = "restaurant.food"
ALCOHOL = "restaurant.alcohol"
GENERIC = "product.generic"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


def option(group: str, name: str, **more) -> str:
    return str(setup("modifier.option.create", {"group": group, "name": name, **more}).id)


@pytest.fixture
def menu(product):
    """«Menu of the day», 13,50 € eaten in: «Starters» (lentils) and «Mains» (hake, or the steak +2,00 €). The steak
    asks «Doneness» (one, required) and «Extras» (cheese +1,00 €, which has milk, and a soda +2,00 € at 21 %)."""
    product("Lentils", "LEN", 500, FOOD, initial_stock="10")
    product("Hake", "HAK", 1400, FOOD, initial_stock="10")
    steak = product("Steak", "STK", 1800, FOOD, initial_stock="10")
    setup("combo.combo.create", {"name": "Menu of the day", "kitchen_name": "MENU", "price": 1350, "tax_category_key": FOOD})
    for group in ("Starters", "Mains"):
        setup("combo.group.create", {"combo": "Menu of the day", "name": group})
    dishes = {}
    for group, sku, delta in (("Starters", "LEN", 0), ("Mains", "HAK", 0), ("Mains", "STK", 200)):
        dishes[sku] = str(
            setup(
                "combo.option.create",
                {"combo": "Menu of the day", "group": group, "product": sku, "price_delta": delta},
            ).id
        )
    setup("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1})
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4})
    options = {
        "rare": option("Doneness", "Rare", kitchen_name="RARE"),
        "done": option("Doneness", "Well done"),
        "cheese": option("Extras", "Cheese", kitchen_name="+CHEESE", price_delta=100, allergens=["milk"]),
        "soda": option("Extras", "Soda", price_delta=200, tax_category_key=GENERIC),
    }
    for group in ("Doneness", "Extras"):
        setup("modifier.link.attach", {"group": group, "product_id": str(steak.id)})
    return dishes, options


@pytest.fixture
def takeaway(product):
    """«Sandwich and beer» to take away, 6,00 €: a sandwich of 4,50 € (food) and a beer of 2,00 € (a restaurant's
    alcohol). The sandwich takes «Extras»: cheese +1,00 € (food, with the sandwich) or a glass of wine +1,50 € (a
    restaurant's alcohol: 21 % to take away, on a line of its own)."""
    sandwich = product("Sandwich", "SAN", 450, FOOD, initial_stock="10")
    product("Beer", "BEE", 200, ALCOHOL, initial_stock="10")
    setup("combo.combo.create", {"name": "Sandwich and beer", "price": 600, "supply_kind": "goods"})
    dishes = {}
    for group, sku in (("Sandwich", "SAN"), ("Drink", "BEE")):
        setup("combo.group.create", {"combo": "Sandwich and beer", "name": group})
        dishes[sku] = str(
            setup("combo.option.create", {"combo": "Sandwich and beer", "group": group, "product": sku}).id
        )
    setup("modifier.group.create", {"name": "Extras", "max_choices": 2})
    options = {
        "cheese": option("Extras", "Cheese", price_delta=100),
        "wine": option("Extras", "Glass of wine", price_delta=150, tax_category_key=ALCOHOL),
    }
    setup("modifier.link.attach", {"group": "Extras", "product_id": str(sandwich.id)})
    return dishes, options


def dish(option_id: str, *option_ids: str, quantity: int = 1) -> dict:
    return {"option_id": option_id, "quantity": quantity, "option_ids": list(option_ids)}


def open_check() -> str:
    return str(run("sale.order.open", {"label": "Table 4"}).id)


def add_menu(order_id: str, *picks: dict, combo: str = "Menu of the day"):
    return run("sale.order.add_combo_line", {"order_id": order_id, "combo": combo, "choices": list(picks)})


def charge(order_id: str, key: str):
    return run("sale.sale.complete", {"idempotency_key": key, "order_id": order_id, "payments": [{"method": "card"}]})


def newest(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload


def test_a_dish_with_a_required_group_left_empty_refuses_the_menu(menu):
    dishes, _options = menu
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"]))
    assert refused.value.code == "modifier.choice_below_min"
    assert "Doneness" in refused.value.message
    assert not Order.objects.get(pk=order_id).lines.exists()


def test_the_options_of_a_dish_are_frozen_under_it_and_add_to_the_menu(menu):
    dishes, options = menu
    order_id = open_check()
    (line,) = add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"], options["cheese"])).lines
    # 13,50 € closed price, the steak's 2,00 € supplement and its cheese, 1,00 €.
    assert (line.unit_price, line.line_total) == (1650, 1650)
    lentils, steak = line.combo.components
    assert (lentils.modifiers, steak.modifiers) == ([], ["Rare", "Cheese"])
    assert steak.allergens == ["milk"]
    assert line.kitchen_text == "Lentils, Steak (RARE, +CHEESE)"


def test_a_dish_without_groups_goes_as_before(menu):
    dishes, _options = menu
    (line,) = add_menu(open_check(), dish(dishes["LEN"]), dish(dishes["HAK"])).lines
    assert (line.unit_price, [d.modifiers for d in line.combo.components]) == (1350, [[], []])


def test_an_option_of_another_dish_is_refused_and_nothing_enters(menu):
    dishes, options = menu
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add_menu(order_id, dish(dishes["LEN"], options["rare"]), dish(dishes["STK"], options["rare"]))
    assert refused.value.code == "modifier.option_not_offered"
    assert not Order.objects.get(pk=order_id).lines.exists()


def test_a_dish_named_by_its_product_takes_its_options_too(menu):
    _dishes, options = menu
    picks = [{"product": "Lentils"}, {"product": "Steak", "option_ids": [options["done"]]}]
    (line,) = run("sale.order.add_combo_line", {"order_id": open_check(), "combo": "Menu of the day", "choices": picks}).lines
    assert [d.modifiers for d in line.combo.components] == [[], ["Well done"]]


def test_eaten_in_the_menu_charges_one_line_with_its_options_inside(menu):
    dishes, options = menu
    order_id = open_check()
    add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"], options["soda"]))
    preview = run("sale.checkout.preview", {"order_id": order_id})
    sale = charge(order_id, "combo-opt-dine-0001")
    # The soda taxes apart sold on its own; inside a menu eaten in it is part of the meal, at the menu's rate.
    assert preview.total == sale.total == 1750
    (charged,) = sale.lines
    assert (charged.name, str(charged.tax_rate), charged.line_total) == ("Menu of the day", "10.00", 1750)
    assert [(d.product_name, d.modifiers) for d in charged.components] == [("Lentils", []), ("Steak", ["Rare", "Soda"])]
    assert [c for line in preview.lines for c in line.components] == ["Lentils", "Steak (Rare, Soda)"]


def test_to_take_away_an_option_of_another_category_charges_its_own_line_under_its_dish(takeaway):
    dishes, options = takeaway
    order_id = open_check()
    add_menu(order_id, dish(dishes["SAN"], options["cheese"], options["wine"]), dish(dishes["BEE"]), combo="Sandwich and beer")
    preview = run("sale.checkout.preview", {"order_id": order_id})
    sale = charge(order_id, "combo-opt-away-0001")
    # 8,50 € over the sandwich with its cheese (5,50 €), its glass of wine (1,50 €) and the beer (2,00 €).
    assert preview.total == sale.total == 850
    lines = sorted(SaleLine.objects.filter(sale_id=sale.id), key=lambda line: line.position)
    assert [(line.name, str(line.tax_rate), line.line_total, line.modifiers) for line in lines] == [
        ("Sandwich", "10.00", 519, ["Cheese"]),
        ("Glass of wine", "21.00", 142, []),
        ("Beer", "21.00", 189, []),
    ]
    sandwich, wine, beer = lines
    assert (wine.parent_line_id, sandwich.parent_line_id, beer.parent_line_id) == (sandwich.id, None, None)
    assert [line.line_total for line in preview.lines] == [519, 142, 189]


def test_the_menu_charges_what_it_was_ordered_at_after_its_option_changes_or_goes(menu):
    dishes, options = menu
    order_id = open_check()
    add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"], options["cheese"]))
    setup("modifier.option.update", {"id": options["cheese"], "price_delta": 900})
    setup("modifier.option.delete", {"id": options["rare"]})
    sale = charge(order_id, "combo-opt-late-0001")
    assert sale.total == 1650
    assert sale.lines[0].components[1].modifiers == ["Rare", "Cheese"]


def test_the_round_fired_names_each_dish_with_its_options(menu):
    dishes, options = menu
    order_id = open_check()
    add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"], options["cheese"]))
    run("sale.order.fire", {"order_id": order_id})
    (item,) = newest("sale.order.fired")["items"]
    assert [(d["product_name"], d["modifiers"]) for d in item["components"]] == [
        ("Lentils", []),
        ("Steak", ["RARE", "+CHEESE"]),
    ]
    assert item["components"][1]["allergens"] == ["milk"]


def test_without_modifiers_a_dish_with_options_is_refused_and_one_without_enters(menu, monkeypatch):
    monkeypatch.setattr("apps.sale.queries.order_lines.MODIFIER_RESOLVE", "modifier.selection.not_installed")
    dishes, options = menu
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"], options["rare"]))
    assert refused.value.code == "sale.modifier_unavailable"
    (line,) = add_menu(order_id, dish(dishes["LEN"]), dish(dishes["STK"])).lines
    assert line.unit_price == 1550
