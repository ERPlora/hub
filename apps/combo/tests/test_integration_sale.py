"""Menus with the real Sales app: the till orders, prices and charges a menu through Menus' own operation
(COMBO-F04, F08, F09; «Contrato con Ventas»).

Sales calls ``combo.combo.resolve`` by name with the seller's session when a menu is ordered (it freezes the
answer on the line) and again when the check is charged, with the amount ordered. What Menus says is what the
ticket says: the closed price plus every supplement, its refusals as they are, and its VAT split — eaten in ONE
line at the menu's rate, to take away one line per dish with the amount split to the cent — that Sales' own
arithmetic turns into base and tax. No doubles: Inventory's products, Taxes' categories and Sales' checks are
made by their own operations.

Traps of the old product: hub#1219 (no sale with a supplement or a menu could be charged) and combos#11 (the
split of a pack is shown before charging, from the same arithmetic that charges it).
"""

import pytest
from live.context import system_context
from live.errors import Conflict

from apps.combo.models import ChoiceGroup, ChoiceOption, Combo

from .conftest import A, ALCOHOL, FOOD, run

pytestmark = pytest.mark.django_db


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


def product(name: str, sku: str, price: int, tax: str = FOOD, **more):
    return setup("inventory.product.create", {"name": name, "sku": sku, "price": price, "tax_category_key": tax, **more})


@pytest.fixture
def day_menu():
    """«Menu of the day», 13,50 € eaten in at restaurant.food: «Starters» (lentils or salad), «Mains» (hake, or
    steak +2,00 €, or a vegetable plate −1,00 €), «Drink» (water or a beer, a restaurant's alcohol) and an
    optional «Coffee» that takes the same coffee twice (+0,50 € each). Returns the choices by SKU."""
    for name, sku, price, tax in (
        ("Lentils", "LEN", 500, FOOD),
        ("Salad", "SAL", 450, FOOD),
        ("Hake", "HAK", 1400, FOOD),
        ("Steak", "STK", 1800, FOOD),
        ("Vegetables", "VEG", 900, FOOD),
        ("Water", "WAT", 150, FOOD),
        ("Beer", "BEE", 250, ALCOHOL),
        ("Coffee", "COF", 150, FOOD),
    ):
        product(name, sku, price, tax)
    setup("combo.combo.create", {"name": "Menu of the day", "kitchen_name": "MENU", "price": 1350, "tax_category_key": FOOD})
    for group, minimum, maximum, repeat in (
        ("Starters", 1, 1, False),
        ("Mains", 1, 1, False),
        ("Drink", 1, 1, False),
        ("Coffee", 0, 2, True),
    ):
        setup(
            "combo.group.create",
            {"combo": "Menu of the day", "name": group, "min_choices": minimum, "max_choices": maximum, "allow_repeat": repeat},
        )
    options = {}
    for group, sku, delta in (
        ("Starters", "LEN", 0),
        ("Starters", "SAL", 0),
        ("Mains", "HAK", 0),
        ("Mains", "STK", 200),
        ("Mains", "VEG", -100),
        ("Drink", "WAT", 0),
        ("Drink", "BEE", 0),
        ("Coffee", "COF", 50),
    ):
        created = setup("combo.option.create", {"combo": "Menu of the day", "group": group, "product": sku, "price_delta": delta})
        options[sku] = str(created.id)
    return options


@pytest.fixture
def pack():
    """«Sandwich and beer» to take away, 6,00 €: a sandwich of 4,50 € (restaurant.food, 10 %) and a beer of
    2,00 € that the bar taxes as a restaurant's alcohol and that leaves at retail.alcohol (21 %)."""
    product("Sandwich", "SAN", 450)
    product("Beer to go", "BTG", 200, ALCOHOL)
    setup("combo.combo.create", {"name": "Sandwich and beer", "price": 600, "supply_kind": "goods"})
    for group, sku in (("Sandwich", "SAN"), ("Drink", "BTG")):
        setup("combo.group.create", {"combo": "Sandwich and beer", "name": group})
        setup("combo.option.create", {"combo": "Sandwich and beer", "group": group, "product": sku})


def picks(options: dict, *skus: str) -> list[dict]:
    return [{"option_id": options[sku]} for sku in skus]


def open_check() -> str:
    return str(run("sale.order.open", {"label": "Table 4"}).id)


def add_menu(order_id: str, choices: list[dict], combo: str = "Menu of the day", quantity: str = "1"):
    return run(
        "sale.order.add_combo_line",
        {"order_id": order_id, "combo": combo, "choices": choices, "quantity": quantity},
    )


def charge(key: str, **source):
    return run("sale.sale.complete", {"idempotency_key": f"combo-sale-{key}", "payments": [{"method": "card"}], **source})


def lines_of(sale) -> list[tuple]:
    """``(name, unit price, tax category, rate, base, tax, total)`` of each line of a charged sale."""
    return [
        (line.name, line.unit_price, line.tax_category_key, line.tax_rate, line.net_amount, line.tax_amount, line.line_total)
        for line in sale.lines
    ]


# ── COMBO-F08: the closed price plus each supplement, Menus' refusals as they are ──────────────────────


def test_combo_f08_the_till_charges_the_closed_price_plus_every_supplement_also_the_repeated_one(day_menu):
    """hub#1219: a menu with supplements is charged; each pick of a repeated choice adds its supplement."""
    order = open_check()
    (line,) = add_menu(order, picks(day_menu, "SAL", "STK", "WAT", "COF", "COF"), quantity="2").lines
    # 13,50 + 2,00 (steak) + 2 × 0,50 (two coffees), per menu; the dishes in the order of the courses.
    assert (line.unit_price, line.quantity) == (1650, 2)
    assert [(dish.product_name, dish.quantity) for dish in line.combo.components] == [
        ("Salad", 1),
        ("Steak", 1),
        ("Water", 1),
        ("Coffee", 2),
    ]

    sale = charge("f08-supplements", order_id=order)

    assert sale.total == 3300
    assert [(row.name, row.quantity, row.line_total) for row in sale.lines] == [("Menu of the day", 2, 3300)]


def test_combo_f08_a_negative_supplement_lowers_the_menu(day_menu):
    sale = charge("f08-negative", combo_lines=[{"combo": "Menu of the day", "choices": picks(day_menu, "LEN", "VEG", "WAT")}])
    assert sale.total == 1250


@pytest.mark.parametrize(
    ("change", "choices", "code"),
    [
        (lambda: ChoiceOption.objects.filter(product__sku="HAK").update(is_available=False), ("LEN", "HAK", "WAT"), "combo.option_sold_out"),
        (lambda: setup("inventory.product.set_sold_out", {"product": "HAK", "sold_out": True}), ("LEN", "HAK", "WAT"), "combo.option_sold_out"),
        (lambda: setup("inventory.product.update", {"product": "HAK", "is_active": False}), ("LEN", "HAK", "WAT"), "combo.product_unavailable"),
        (lambda: Combo.objects.update(is_active=False), ("LEN", "HAK", "WAT"), "combo.not_on_sale"),
        (lambda: None, ("LEN", "WAT"), "combo.group_incomplete"),
        (lambda: None, ("LEN", "SAL", "HAK", "WAT"), "combo.group_too_many"),
        (lambda: ChoiceGroup.objects.filter(name="Drink").update(max_choices=2), ("LEN", "HAK", "WAT", "WAT"), "combo.group_no_repeat"),
        (lambda: None, (), "combo.nothing_picked"),
    ],
)
def test_combo_f08_menus_refusal_reaches_the_seller_as_it_is_and_the_check_stays_as_it_was(day_menu, change, choices, code):
    order = open_check()
    change()
    with pytest.raises(Conflict) as refused:
        add_menu(order, picks(day_menu, *choices))
    assert refused.value.code == code
    assert run("sale.order.get", {"order_id": order}).lines == []


def test_combo_f08_a_dish_that_is_not_of_this_menu_is_refused(day_menu):
    product("Pizza", "PIZ", 1100)
    order = open_check()
    with pytest.raises(Conflict) as refused:
        add_menu(order, [{"product": "LEN"}, {"product": "HAK"}, {"product": "PIZ"}])
    assert refused.value.code == "combo.option_not_in_combo"


def test_combo_f08_an_open_check_charges_what_was_ordered_though_the_dish_ran_out_and_the_price_went_up(day_menu):
    """The last flan served and marked sold out does not stop the table paying; the price ordered holds."""
    order = open_check()
    add_menu(order, picks(day_menu, "LEN", "STK", "WAT"))
    ChoiceOption.objects.filter(product__sku="STK").update(is_available=False)
    setup("combo.combo.update", {"combo": "Menu of the day", "price": 1500, "is_active": False})

    sale = charge("f08-ordered", order_id=order)

    assert sale.total == 1550


def test_combo_f04_a_menu_withdrawn_after_ordering_is_charged_as_it_was_ordered(day_menu):
    """A ticket already issued keeps its copy of the menu, and so does an open check (SALE-F12)."""
    order = open_check()
    add_menu(order, picks(day_menu, "LEN", "HAK", "BEE"))
    setup("combo.combo.delete", {"combo": "Menu of the day"})

    sale = charge("f04-withdrawn", order_id=order)

    assert lines_of(sale) == [("Menu of the day", 1350, FOOD, 10, 1227, 123, 1350)]
    assert [dish.product_name for dish in sale.lines[0].components] == ["Lentils", "Hake", "Beer"]


# ── COMBO-F09: the VAT of a menu, as Sales bills it ──────────────────────────────────────────────────


def test_combo_f09_eaten_in_is_one_line_at_the_menus_rate_the_beer_included(day_menu):
    """Art. 91.Uno.2.2º LIVA: the drink of a menu served at the table, beer included, is part of one service."""
    sale = charge("f09-eaten-in", combo_lines=[{"combo": "Menu of the day", "choices": picks(day_menu, "LEN", "HAK", "BEE")}])

    assert lines_of(sale) == [("Menu of the day", 1350, FOOD, 10, 1227, 123, 1350)]
    assert [(row.rate_pct, row.base, row.tax) for row in sale.breakdown] == [(10, 1227, 123)]


def test_combo_f09_a_pack_to_take_away_is_one_line_per_dish_split_to_the_cent(pack):
    """Art. 79.Dos LIVA: 6,00 € split by catalogue price, 4,50 and 2,00 → 4,15 + 1,85, the beer at 21 %; no line
    of the menu carries money."""
    sale = charge(
        "f09-pack",
        combo_lines=[{"combo": "Sandwich and beer", "choices": [{"product": "SAN"}, {"product": "BTG"}], "quantity": "2"}],
    )

    assert lines_of(sale) == [
        ("Sandwich", 415, FOOD, 10, 755, 75, 830),
        ("Beer to go", 185, "retail.alcohol", 21, 306, 64, 370),
    ]
    assert {line.combo_name for line in sale.lines} == {"Sandwich and beer"}
    assert sale.total == 1200 == sum(line.line_total for line in sale.lines)
    assert sorted((row.rate_pct, row.base, row.tax) for row in sale.breakdown) == [(10, 755, 75), (21, 306, 64)]
    assert sale.subtotal + sale.tax_total == sale.total


def test_combo_f09_a_pack_whose_dishes_go_at_the_same_rate_is_one_line(pack):
    product("Juice", "JUI", 200)
    setup("combo.option.create", {"combo": "Sandwich and beer", "group": "Drink", "product": "JUI"})

    sale = charge("f09-one-rate", combo_lines=[{"combo": "Sandwich and beer", "choices": [{"product": "SAN"}, {"product": "JUI"}]}])

    assert lines_of(sale) == [("Sandwich and beer", 600, FOOD, 10, 545, 55, 600)]


def test_combo_f09_the_split_shown_before_charging_is_the_split_charged(pack):
    """combos#11: the bill shown before charging (Sales' preview) splits the pack exactly as the charge does."""
    order = open_check()
    add_menu(order, [{"product": "SAN"}, {"product": "BTG"}], combo="Sandwich and beer", quantity="3")

    preview = run("sale.checkout.preview", {"order_id": order})
    sale = charge("f09-preview", order_id=order)

    shown = [
        (line.name, line.unit_price, line.tax_category_key, line.net_amount, line.tax_amount, line.line_total, line.combo_name)
        for line in preview.lines
    ]
    charged = [
        (line.name, line.unit_price, line.tax_category_key, line.net_amount, line.tax_amount, line.line_total, line.combo_name)
        for line in sale.lines
    ]
    assert shown == charged
    assert shown[0][:3] == ("Sandwich", 415, FOOD)
    assert (preview.total, preview.subtotal, preview.tax_total) == (sale.total, sale.subtotal, sale.tax_total) == (1800, 1591, 209)
