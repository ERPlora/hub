"""The line of a menu with what was picked (COMBO-F08, F09).

The choices are real Inventory products; the tax categories, Taxes' own. ``split_amount`` is the VAT
split of a menu sold to take away (art. 79.Dos LIVA): proportional to the catalogue prices, the cents
left over to the largest remainders, the sum exactly the amount.
"""

import pytest
from live.errors import Conflict

from apps.combo.queries.lines import split_amount

from .conftest import (
    ALCOHOL,
    ALCOHOL_TO_GO,
    FOOD,
    GENERIC,
    HUB_DB,
    ctx_for,
    make_combo,
    make_group,
    make_option,
    make_product,
    menu_of_the_day,
    pick,
    refusal,
    run,
    sandwich_and_beer,
    tax_category,
)

pytestmark = HUB_DB


# split_amount


@pytest.mark.parametrize(
    ("total", "weights", "shares"),
    [
        # The reference case: 6,00 € over a 4,50 € sandwich and a 2,00 € beer.
        (600, [450, 200], [415, 185]),
        # Odoo's documented example: 120 over 100 and 50.
        (120, [100, 50], [80, 40]),
        # HMRC's meal deal (VATVAL03800): 10 over 6, 1,50, 1,50 and 6.
        (1000, [600, 150, 150, 600], [400, 100, 100, 400]),
        # A tie goes to the first chosen.
        (100, [1, 1, 1], [34, 33, 33]),
        # A component at 0 € takes nothing.
        (500, [300, 0, 200], [300, 0, 200]),
        (0, [300, 200], [0, 0]),
    ],
)
def test_split_amount_is_proportional_and_adds_up_exactly(total, weights, shares):
    assert split_amount(total, weights) == shares
    assert sum(split_amount(total, weights)) == total


# combo.combo.resolve (COMBO-F08, F09)


def test_a_menu_eaten_in_is_one_line_at_its_own_category_whatever_the_dishes():
    combo, groups, products, options = menu_of_the_day()
    line = run(
        "combo.combo.resolve",
        {
            "id": str(combo.id),
            "choices": pick(options["wine"], options["hake"], options["salad"]),
        },
        ctx_for("hub_employee"),
    )
    assert (line.combo_id, line.name, line.kitchen_name, line.supply_kind) == (
        combo.id,
        "Menu of the day",
        "MENU",
        "service",
    )
    assert (line.price, line.supplements, line.amount) == (1350, 150, 1500)
    assert line.split is False
    assert line.tax_category_key == FOOD
    # In the order of the courses, whatever the order picked.
    assert [
        (c.group_name, c.product_name, c.quantity, c.price_delta, c.amount)
        for c in line.components
    ] == [
        ("Starters", "Salad", 1, -50, None),
        ("Mains", "Hake", 1, 200, None),
        ("Drink", "House wine", 1, 0, None),
    ]
    wine = line.components[2]
    assert (
        wine.product_id,
        wine.sku,
        wine.catalog_price,
        wine.tax_category_key,
        wine.is_service,
    ) == (
        products["wine"].id,
        "WIN",
        300,
        ALCOHOL,
        False,
    )


def test_picks_are_named_by_the_product_as_said():
    combo, groups, products, options = menu_of_the_day()
    line = run(
        "combo.combo.resolve",
        {
            "combo": "menu of the day",
            "choices": [
                {"product": "lentils"},
                {"product": "HAK"},
                {"product": "Water"},
            ],
        },
    )
    assert [c.product_name for c in line.components] == ["Lentils", "Hake", "Water"]


def test_a_product_in_two_courses_is_named_with_its_course():
    combo, groups, products, options = menu_of_the_day()
    make_option(groups["mains"], products["lentils"])
    choices = [{"product": "Lentils"}, {"product": "Hake"}, {"product": "Water"}]
    with pytest.raises(Conflict) as caught:
        run("combo.combo.resolve", {"id": str(combo.id), "choices": choices})
    assert caught.value.code == "combo.option_ambiguous"
    choices[0]["group"] = "starters"
    assert (
        run("combo.combo.resolve", {"id": str(combo.id), "choices": choices})
        .components[0]
        .group_name
        == "Starters"
    )


def test_a_repeated_pick_counts_its_supplement_each_time():
    combo = make_combo("Breakfast", price=500)
    coffee_course = make_group(
        combo, "Coffee", min_choices=2, max_choices=2, allow_repeat=True
    )
    coffee = make_option(
        coffee_course, make_product("Coffee", price=150), price_delta=30
    )
    line = run(
        "combo.combo.resolve",
        {"id": str(combo.id), "choices": pick(coffee, quantity=2)},
    )
    assert (line.supplements, line.amount) == (60, 560)
    assert [(c.product_name, c.quantity) for c in line.components] == [("Coffee", 2)]
    # The same choice named twice adds up.
    again = run(
        "combo.combo.resolve",
        {"id": str(combo.id), "choices": pick(coffee) + pick(coffee)},
    )
    assert again.components[0].quantity == 2


def test_to_take_away_with_one_category_is_one_line_at_it():
    combo = make_combo("Sandwich pack", price=600, supply_kind="goods")
    make_option(
        make_group(combo, "Sandwich"),
        make_product("Ham sandwich", price=450, tax=GENERIC),
    )
    make_option(
        make_group(combo, "Drink"), make_product("Cola", price=200, tax=GENERIC)
    )
    line = run(
        "combo.combo.resolve",
        {
            "id": str(combo.id),
            "choices": [{"product": "Ham sandwich"}, {"product": "Cola"}],
        },
    )
    assert (line.split, line.tax_category_key, line.amount) == (False, GENERIC, 600)
    assert [c.amount for c in line.components] == [None, None]


def test_to_take_away_with_several_categories_splits_the_amount_per_dish():
    combo = make_combo("Sandwich pack", price=600, supply_kind="goods")
    make_option(
        make_group(combo, "Sandwich"), make_product("Ham sandwich", price=450, tax=FOOD)
    )
    make_option(
        make_group(combo, "Drink"), make_product("Beer", price=200, tax=ALCOHOL)
    )
    line = run(
        "combo.combo.resolve",
        {
            "id": str(combo.id),
            "choices": [{"product": "Beer"}, {"product": "Ham sandwich"}],
        },
    )
    assert (line.split, line.tax_category_key, line.amount) == (True, None, 600)
    assert [
        (c.product_name, c.tax_category_key, c.amount) for c in line.components
    ] == [
        ("Ham sandwich", FOOD, 415),
        ("Beer", ALCOHOL_TO_GO, 185),
    ]


def test_an_open_check_splits_the_amount_it_was_ordered_at():
    combo = make_combo("Sandwich pack", price=600, supply_kind="goods")
    make_option(
        make_group(combo, "Sandwich"), make_product("Ham sandwich", price=450, tax=FOOD)
    )
    make_option(
        make_group(combo, "Drink"), make_product("Beer", price=200, tax=ALCOHOL)
    )
    combo.price = 700
    combo.save()
    line = run(
        "combo.combo.resolve",
        {
            "id": str(combo.id),
            "choices": [{"product": "Ham sandwich"}, {"product": "Beer"}],
            "amount": 600,
        },
    )
    assert (line.price, line.amount) == (700, 600)
    assert sum(c.amount for c in line.components) == 600


def test_a_menu_off_sale_or_unknown_is_refused():
    combo, groups, products, options = menu_of_the_day()
    combo.is_active = False
    combo.save()
    error = refusal(combo, pick(options["lentils"], options["hake"], options["water"]))
    assert (error.code, error.message) == (
        "combo.not_on_sale",
        "That menu is no longer on sale.",
    )
    # A menu that no longer exists is the till's 409 (a 404 is also «app inactive»).
    with pytest.raises(Conflict) as missing:
        run("combo.combo.resolve", {"combo": "brunch"})
    assert (missing.value.code, missing.value.message) == (
        "combo.combo_missing",
        "That menu does not exist in this business.",
    )


def test_nothing_picked_is_refused():
    combo, *_ = menu_of_the_day()
    error = refusal(combo, [])
    assert (error.code, error.message) == (
        "combo.nothing_picked",
        "Pick something from the menu before adding it.",
    )


def test_each_course_keeps_its_rules():
    combo, groups, products, options = menu_of_the_day()
    short = refusal(combo, pick(options["lentils"], options["water"]))
    assert (short.code, short.message) == (
        "combo.group_incomplete",
        "The menu still needs a pick in “Mains”: pick 1.",
    )
    over = refusal(
        combo,
        pick(options["lentils"], options["salad"], options["hake"], options["water"]),
    )
    assert (over.code, over.message) == (
        "combo.group_too_many",
        "The course “Starters” takes 1 at most.",
    )
    groups["starters"].max_choices = 2
    groups["starters"].save()
    twice = refusal(
        combo,
        pick(options["lentils"], quantity=2) + pick(options["hake"], options["water"]),
    )
    assert (twice.code, twice.message) == (
        "combo.group_no_repeat",
        "The course “Starters” does not take the same choice twice.",
    )


def test_a_choice_of_another_menu_is_refused():
    combo, groups, products, options = menu_of_the_day()
    other = make_option(make_group(make_combo("Kids menu")), make_product("Nuggets"))
    error = refusal(
        combo, pick(other, options["lentils"], options["hake"], options["water"])
    )
    assert error.code == "combo.option_not_in_combo"
    named = refusal(combo, [{"product": "Nuggets"}])
    assert (named.code, named.message) == (
        "combo.option_not_in_combo",
        "“Nuggets” is not a choice of this menu.",
    )


def test_a_choice_that_cannot_be_sold_is_refused():
    combo, groups, products, options = menu_of_the_day()
    options["lentils"].is_available = False
    options["lentils"].save()
    sold_out = refusal(
        combo, pick(options["lentils"], options["hake"], options["water"])
    )
    assert (sold_out.code, sold_out.message) == (
        "combo.option_sold_out",
        "“Lentils” is sold out.",
    )
    products["hake"].is_active = False
    products["hake"].save()
    gone = refusal(combo, pick(options["salad"], options["hake"], options["water"]))
    assert (gone.code, gone.message) == (
        "combo.product_unavailable",
        "“Hake” can no longer be sold: it is deactivated or deleted in Inventory.",
    )


def test_a_negative_amount_is_refused():
    combo = make_combo("Cheap", price=100)
    option = make_option(make_group(combo), make_product(), price_delta=-150)
    error = refusal(combo, pick(option))
    assert (error.code, error.message) == (
        "combo.amount_negative",
        "The menu's amount cannot be negative.",
    )


def test_to_take_away_every_dish_needs_its_tax_category():
    combo = make_combo("Pack", price=600, supply_kind="goods")
    option = make_option(make_group(combo), make_product("Mystery box", tax=None))
    error = refusal(combo, pick(option))
    assert (error.code, error.message) == (
        "combo.tax_category_missing",
        "“Mystery box” has no tax category in Inventory, so this menu cannot be charged.",
    )


def test_a_split_needs_some_catalogue_price():
    combo = make_combo("Pack", price=600, supply_kind="goods")
    a = make_option(make_group(combo, "A"), make_product("Free A", price=0, tax=FOOD))
    b = make_option(
        make_group(combo, "B"), make_product("Free B", price=0, tax=ALCOHOL)
    )
    error = refusal(combo, pick(a, b))
    assert error.code == "combo.no_catalog_price"


def test_a_menu_eaten_in_with_a_deactivated_tax_category_is_refused():
    combo = make_combo(tax_category=tax_category("e2e.combo_old"))
    option = make_option(make_group(combo), make_product())
    combo.tax_category.is_active = False
    combo.tax_category.save()
    assert refusal(combo, pick(option)).code == "combo.tax_category_missing"


# Eaten in or to take away: the menu's setting, unless Sales says how this line is sold


CHOICES = [{"product": "Ham sandwich"}, {"product": "Beer"}]


def test_to_take_away_a_beer_of_the_premises_goes_at_the_rate_of_a_sale_of_goods():
    line = run("combo.combo.resolve", {"id": str(sandwich_and_beer().id), "choices": CHOICES})
    assert [(c.product_name, c.tax_category_key) for c in line.components] == [
        ("Ham sandwich", FOOD),
        ("Beer", ALCOHOL_TO_GO),
    ]


def test_a_menu_eaten_in_ordered_to_take_away_is_split_per_dish():
    combo = sandwich_and_beer("service")
    line = run("combo.combo.resolve", {"id": str(combo.id), "choices": CHOICES, "channel": "takeaway"})
    assert (line.supply_kind, line.split, line.tax_category_key) == ("goods", True, None)
    assert [(c.tax_category_key, c.amount) for c in line.components] == [(FOOD, 415), (ALCOHOL_TO_GO, 185)]
    delivered = run("combo.combo.resolve", {"id": str(combo.id), "choices": CHOICES, "channel": "delivery"})
    assert delivered.split is True


def test_a_menu_eaten_in_stays_one_line_on_the_premises():
    combo = sandwich_and_beer("service")
    for channel in (None, "dine_in"):
        params = {"id": str(combo.id), "choices": CHOICES, **({"channel": channel} if channel else {})}
        line = run("combo.combo.resolve", params)
        assert (line.supply_kind, line.split, line.tax_category_key) == ("service", False, FOOD)


def test_a_pack_without_a_rate_of_its_own_eaten_in_is_billed_per_dish_at_their_premises_rates():
    line = run("combo.combo.resolve", {"id": str(sandwich_and_beer().id), "choices": CHOICES, "channel": "dine_in"})
    assert line.supply_kind == "goods"
    assert [c.tax_category_key for c in line.components] == [FOOD, ALCOHOL]


def test_without_an_equivalent_to_take_away_the_line_is_refused():
    retail = tax_category(ALCOHOL_TO_GO)
    retail.is_active = False
    retail.save()
    error = refusal(sandwich_and_beer(), CHOICES)
    assert error.code == "combo.tax_category_takeaway"
    assert error.message == (
        "“Beer” is billed at restaurant.alcohol, which has no equivalent to take away in Taxes, "
        "so this menu cannot be sold to take away."
    )


# An open check is charged at what was ordered, even if a dish ran out since


def test_charging_an_open_check_does_not_ask_for_availability_again():
    combo, groups, products, options = menu_of_the_day()
    options["lentils"].is_available = False
    options["lentils"].save()
    products["hake"].is_active = False
    products["hake"].save()
    combo.is_active = False
    combo.save()
    line = run(
        "combo.combo.resolve",
        {"id": str(combo.id), "choices": pick(options["lentils"], options["hake"], options["water"]), "amount": 1550},
    )
    assert (line.amount, line.tax_category_key) == (1550, FOOD)
    # Without the amount it is a new order, and those are refused.
    assert refusal(combo, pick(options["lentils"], options["hake"], options["water"])).code == "combo.not_on_sale"


def test_charging_an_open_check_still_checks_the_courses_and_the_tax():
    combo, groups, products, options = menu_of_the_day()
    assert refusal(combo, pick(options["lentils"]), amount=1350).code == "combo.group_incomplete"
    combo.tax_category.is_active = False
    combo.tax_category.save()
    assert refusal(combo, pick(options["lentils"], options["hake"], options["water"]), amount=1350).code == (
        "combo.tax_category_missing"
    )
