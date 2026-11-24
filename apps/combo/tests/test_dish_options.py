"""The options of Modifiers chosen for a dish of a menu, as Menus prices the line with them (SALE-F42; COMBO-F08, F09).

Sales asks Modifiers to check and value the options of each dish and hands them to ``combo.combo.resolve`` with the
dish. Menus adds them to the menu's amount once per pick of the dish. Eaten in, the menu stays one line at its own
rate with the options inside, also one of another tax category. To take away, an option of the dish's category goes
with its dish and weighs its price with it; one of another category goes to that category's takeaway equivalent,
weighs its own price and gets its own part of the amount. Charging an open check keeps the amount ordered and splits it
the same way with the options the line froze.
"""

from uuid import uuid7

import pytest
from live.errors import Conflict

from apps.combo.queries.dish_options import TAKEAWAY_CATEGORY
from apps.tax.models import TaxCategory

from .conftest import (
    ALCOHOL,
    ALCOHOL_TO_GO,
    FOOD,
    HUB_DB,
    make_combo,
    make_group,
    make_option,
    make_product,
    run,
)

pytestmark = HUB_DB


def valued(name: str, price_delta: int = 0, *, tax: str | None = None, own_line: bool = False) -> dict:
    """An option as Modifiers values it for a dish (``modifier.selection.resolve``)."""
    return {
        "option_id": str(uuid7()),
        "name": name,
        "kitchen_name": name.upper(),
        "price_delta": price_delta,
        "tax_category_key": tax,
        "own_line": own_line,
        "allergens": ["milk"] if name == "Cheese" else [],
    }


def steak_menu():
    """«Steak menu», 15,00 € eaten in: the steak (+2,00 €) or the hake, and two coffees at most."""
    combo = make_combo("Steak menu", price=1500)
    mains = make_group(combo, "Mains")
    coffees = make_group(combo, "Coffee", min_choices=0, max_choices=2, allow_repeat=True)
    return {
        "combo": combo,
        "steak": make_option(mains, make_product("Steak", price=1800), price_delta=200),
        "hake": make_option(mains, make_product("Hake", price=1400)),
        "coffee": make_option(coffees, make_product("Coffee", price=150)),
    }


def sandwich_pack(supply_kind: str = "goods"):
    """«Sandwich pack», 6,00 € to take away: a sandwich of 4,50 € (food) and a beer of 2,00 € (a restaurant's alcohol,
    retail alcohol to take away)."""
    combo = make_combo("Sandwich pack", price=600, supply_kind=supply_kind)
    return {
        "combo": combo,
        "sandwich": make_option(make_group(combo, "Sandwich"), make_product("Sandwich", price=450, tax=FOOD)),
        "beer": make_option(make_group(combo, "Drink"), make_product("Beer", price=200, tax=ALCOHOL)),
    }


def resolve(combo, *choices, **more):
    return run("combo.combo.resolve", {"id": str(combo.id), "choices": list(choices), **more})


def dish(option, *options, quantity: int = 1) -> dict:
    return {"option_id": str(option.id), "quantity": quantity, "options": list(options)}


def test_the_options_add_to_the_amount_once_per_pick_of_their_dish():
    menu = steak_menu()
    rare, sauce, oat = valued("Rare"), valued("Pepper sauce", 150), valued("Oat milk", 30)
    line = resolve(menu["combo"], dish(menu["steak"], rare, sauce), dish(menu["coffee"], oat, quantity=2))
    # 15,00 € + the steak's 2,00 € + its sauce 1,50 € + 0,30 € of oat milk in each of the two coffees.
    assert (line.price, line.supplements, line.amount) == (1500, 200, 1910)
    assert (line.split, line.tax_category_key) == (False, FOOD)
    steak, coffee = line.components
    assert [(o.name, o.kitchen_name, o.price_delta, o.amount) for o in steak.options] == [
        ("Rare", "RARE", 0, None),
        ("Pepper sauce", "PEPPER SAUCE", 150, None),
    ]
    assert [o.name for o in coffee.options] == ["Oat milk"]


def test_a_dish_without_options_is_priced_as_before():
    menu = steak_menu()
    line = resolve(menu["combo"], dish(menu["hake"]))
    assert (line.amount, line.components[0].options) == (1500, [])


def test_eaten_in_an_option_of_another_category_stays_inside_the_one_line_of_the_menu():
    menu = steak_menu()
    wine = valued("Glass of wine", 250, tax=ALCOHOL, own_line=True)
    line = resolve(menu["combo"], dish(menu["steak"], wine))
    assert (line.split, line.tax_category_key, line.amount) == (False, FOOD, 1950)
    (option,) = line.components[0].options
    assert (option.tax_category_key, option.line_tax_category_key, option.amount) == (ALCOHOL, None, None)


def test_to_take_away_an_option_of_its_dishs_category_weighs_with_the_dish():
    pack = sandwich_pack()
    cheese = valued("Cheese", 100)
    line = resolve(pack["combo"], dish(pack["sandwich"], cheese), dish(pack["beer"]))
    # 7,00 € over the sandwich with its cheese (5,50 €) and the beer (2,00 €): 5,13 € + 1,87 €.
    assert (line.split, line.amount) == (True, 700)
    assert [(c.product_name, c.tax_category_key, c.amount) for c in line.components] == [
        ("Sandwich", FOOD, 513),
        ("Beer", ALCOHOL_TO_GO, 187),
    ]
    assert [(o.name, o.amount, o.line_tax_category_key) for o in line.components[0].options] == [("Cheese", None, None)]


def test_to_take_away_an_option_of_another_category_gets_its_own_part_at_its_takeaway_category():
    pack = sandwich_pack()
    wine = valued("Glass of wine", 150, tax=ALCOHOL, own_line=True)
    line = resolve(pack["combo"], dish(pack["sandwich"], wine), dish(pack["beer"]))
    # 7,50 € over the sandwich (4,50 €), its glass of wine (1,50 €) and the beer (2,00 €): 4,22 € + 1,41 € + 1,87 €.
    assert (line.split, line.amount) == (True, 750)
    sandwich, beer = line.components
    assert (sandwich.amount, beer.amount) == (422, 187)
    (own,) = sandwich.options
    assert (own.tax_category_key, own.line_tax_category_key, own.amount) == (ALCOHOL, ALCOHOL_TO_GO, 141)
    assert sandwich.amount + own.amount + beer.amount == line.amount


def test_to_take_away_a_menu_whose_dish_and_options_share_a_category_stays_one_line():
    combo = make_combo("Burger pack", price=900, supply_kind="goods")
    burger = make_option(make_group(combo, "Burger"), make_product("Burger", price=800, tax=FOOD))
    line = resolve(combo, dish(burger, valued("Cheese", 100)))
    assert (line.split, line.tax_category_key, line.amount) == (False, FOOD, 1000)


def test_to_take_away_an_option_with_no_takeaway_category_is_refused_naming_it():
    TaxCategory.objects.filter(key=ALCOHOL_TO_GO).update(is_active=False)
    combo = make_combo("Burger pack", price=900, supply_kind="goods")
    burger = make_option(make_group(combo, "Burger"), make_product("Burger", price=800, tax=FOOD))
    with pytest.raises(Conflict) as caught:
        resolve(combo, dish(burger, valued("Glass of wine", 150, tax=ALCOHOL, own_line=True)))
    assert caught.value.code == "combo.tax_category_takeaway"
    assert "Glass of wine" in caught.value.message


def test_charging_an_open_check_keeps_the_amount_and_splits_it_with_the_frozen_options():
    pack = sandwich_pack()
    wine = valued("Glass of wine", 150, tax=ALCOHOL, own_line=True)
    pack["combo"].price = 800
    pack["combo"].save()
    line = resolve(pack["combo"], dish(pack["sandwich"], wine), dish(pack["beer"]), amount=750)
    assert line.amount == 750
    sandwich, beer = line.components
    assert (sandwich.amount, sandwich.options[0].amount, beer.amount) == (422, 141, 187)


def test_two_picks_naming_one_dish_carry_the_options_of_both():
    menu = steak_menu()
    milk, sugar = valued("Milk", 20), valued("Sugar")
    line = resolve(menu["combo"], dish(menu["steak"]), dish(menu["coffee"], milk), dish(menu["coffee"], sugar))
    coffee = line.components[1]
    assert (coffee.quantity, [o.name for o in coffee.options]) == (2, ["Milk", "Sugar"])
    assert line.amount == 1500 + 200 + 2 * 20


def test_the_takeaway_map_is_explicit():
    assert TAKEAWAY_CATEGORY == {"restaurant.alcohol": "retail.alcohol"}
