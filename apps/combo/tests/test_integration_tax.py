"""Menus with the real Taxes app: its factory categories and rates bill each line (COMBO-F09).

A menu eaten in is one line at its own category, restaurant.food at 10 %, wine included (art.
91.Uno.2.2 LIVA). A pack to take away whose dishes are at different categories is split in proportion
to their catalogue prices, and each part priced by Taxes at its own rate (art. 79.Dos): a beer to take
away is retail.alcohol at 21 % even when the catalogue tags it restaurant.alcohol, as a restaurant does
(Taxes' factory alias «beer»). Eaten in or to take away is what Ventas says for the line (its order's
channel), the menu's setting otherwise. The VAT of the parts is what Ventas will charge (VAT included).
"""

import pytest
from live.errors import InvalidPayload

from .conftest import ALCOHOL, ALCOHOL_TO_GO, FOOD, ctx_for, run

pytestmark = pytest.mark.django_db


def vat(amount: int, key: str) -> tuple[int, int, str]:
    """Base, tax and rate of ``amount`` (VAT included) at ``key``, as Taxes calculates them."""
    out = run(
        "tax.rate.calculate",
        {
            "amount": amount,
            "tax_category_key": key,
            "tax_included": True,
            "date": "2026-10-15",
        },
        ctx_for("hub_employee"),
    )
    return out.base, out.tax, f"{out.tax_rate_pct:.0f}"


def product(name: str, sku: str, price: int, key: str) -> None:
    run(
        "inventory.product.create",
        {"name": name, "sku": sku, "price": price, "tax_category_key": key},
    )


def test_the_menu_eaten_in_is_one_line_at_ten_percent_wine_included():
    product("Lentils", "LEN", 700, FOOD)
    product("House wine", "WIN", 300, ALCOHOL)
    run(
        "combo.combo.create",
        {"name": "Menu of the day", "price": 1350, "tax_category_key": FOOD},
    )
    run("combo.group.create", {"combo": "Menu of the day", "name": "Starters"})
    run("combo.group.create", {"combo": "Menu of the day", "name": "Drink"})
    run(
        "combo.option.create",
        {"combo": "Menu of the day", "group": "Starters", "product": "LEN"},
    )
    run(
        "combo.option.create",
        {"combo": "Menu of the day", "group": "Drink", "product": "WIN"},
    )
    line = run(
        "combo.combo.resolve",
        {
            "combo": "Menu of the day",
            "choices": [{"product": "LEN"}, {"product": "WIN"}],
        },
    )
    assert (line.split, line.tax_category_key, line.amount) == (False, FOOD, 1350)
    assert vat(line.amount, line.tax_category_key) == (1227, 123, "10")


def test_the_pack_to_take_away_is_split_and_each_part_taxed_at_its_rate():
    product("Ham sandwich", "SAN", 450, FOOD)
    product("Beer", "BEE", 200, ALCOHOL)
    run(
        "combo.combo.create",
        {"name": "Sandwich pack", "price": 600, "supply_kind": "goods"},
    )
    run("combo.group.create", {"combo": "Sandwich pack", "name": "Sandwich"})
    run("combo.group.create", {"combo": "Sandwich pack", "name": "Drink"})
    run(
        "combo.option.create",
        {"combo": "Sandwich pack", "group": "Sandwich", "product": "SAN"},
    )
    run(
        "combo.option.create",
        {"combo": "Sandwich pack", "group": "Drink", "product": "BEE"},
    )
    line = run(
        "combo.combo.resolve",
        {"combo": "Sandwich pack", "choices": [{"product": "SAN"}, {"product": "BEE"}]},
    )
    assert line.split is True
    parts = [(c.amount, c.tax_category_key) for c in line.components]
    assert parts == [(415, FOOD), (185, ALCOHOL_TO_GO)]
    assert [vat(amount, key) for amount, key in parts] == [
        (377, 38, "10"),
        (153, 32, "21"),
    ]
    # Nothing is lost on the way: the parts add up to the closed price.
    assert sum(amount for amount, _ in parts) == 600


def test_a_tax_category_taxes_does_not_know_is_refused():
    with pytest.raises(InvalidPayload) as caught:
        run(
            "combo.combo.create",
            {"name": "Menu", "price": 1000, "tax_category_key": "restaurant.unknown"},
        )
    assert set(caught.value.fields) == {"tax_category_key"}


def lunch_menu_with_beer() -> None:
    product("Ham sandwich", "SAN", 450, FOOD)
    product("Beer", "BEE", 200, ALCOHOL)
    run("combo.combo.create", {"name": "Lunch", "price": 600, "tax_category_key": FOOD})
    run("combo.group.create", {"combo": "Lunch", "name": "Sandwich"})
    run("combo.group.create", {"combo": "Lunch", "name": "Drink"})
    run("combo.option.create", {"combo": "Lunch", "group": "Sandwich", "product": "SAN"})
    run("combo.option.create", {"combo": "Lunch", "group": "Drink", "product": "BEE"})


def test_a_restaurant_beer_is_ten_percent_at_the_table_and_twenty_one_to_take_away():
    lunch_menu_with_beer()
    choices = [{"product": "SAN"}, {"product": "BEE"}]
    at_table = run("combo.combo.resolve", {"combo": "Lunch", "choices": choices, "channel": "dine_in"})
    assert (at_table.split, at_table.tax_category_key) == (False, FOOD)
    assert vat(at_table.amount, at_table.tax_category_key) == (545, 55, "10")
    # The same menu ordered to take away: split, and the beer at the rate of a sale of goods.
    to_go = run("combo.combo.resolve", {"combo": "Lunch", "choices": choices, "channel": "takeaway"})
    assert to_go.split is True
    parts = [(c.amount, c.tax_category_key) for c in to_go.components]
    assert parts == [(415, FOOD), (185, ALCOHOL_TO_GO)]
    assert [vat(amount, key)[2] for amount, key in parts] == ["10", "21"]
