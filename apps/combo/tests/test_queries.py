"""Reads of the combo app: the list of menus, one menu with its courses and choices, the till's catalogue
and the line of a menu with what was picked (WORKBOOK COMBO-F01, F05–F09, F12, F13).

The choices are real Inventory products; the tax categories, Taxes' own. ``split_amount`` is the VAT
split of a menu sold to take away (art. 79.Dos LIVA): proportional to the catalogue prices, the cents
left over to the largest remainders, the sum exactly the amount.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from live.errors import Conflict, NotFound, PermissionDenied

from apps.combo.queries import split_amount

from .conftest import (
    ALCOHOL,
    ALCOHOL_TO_GO,
    DRINK,
    FOOD,
    GENERIC,
    ctx_for,
    make_combo,
    make_group,
    make_option,
    make_product,
    run,
    tax_category,
)

pytestmark = pytest.mark.django_db


def menu_of_the_day():
    """«Menu of the day», 13,50 € eaten in: Starters (lentils, salad −0,50 €), Mains (hake +2 €, chicken),
    Drink (water, wine), each one compulsory pick."""
    combo = make_combo("Menu of the day", price=1350, kitchen_name="MENU")
    starters = make_group(combo, "Starters")
    mains = make_group(combo, "Mains")
    drink = make_group(combo, "Drink")
    products = {
        "lentils": make_product("Lentils", price=700, sku="LEN"),
        "salad": make_product("Salad", price=650, sku="SAL"),
        "hake": make_product("Hake", price=1400, sku="HAK"),
        "chicken": make_product("Chicken", price=1100, sku="CHI"),
        "water": make_product("Water", price=200, sku="WAT", tax=DRINK),
        "wine": make_product("House wine", price=300, sku="WIN", tax=ALCOHOL),
    }
    options = {
        "lentils": make_option(starters, products["lentils"]),
        "salad": make_option(starters, products["salad"], price_delta=-50),
        "hake": make_option(mains, products["hake"], price_delta=200),
        "chicken": make_option(mains, products["chicken"]),
        "water": make_option(drink, products["water"]),
        "wine": make_option(drink, products["wine"]),
    }
    return (
        combo,
        {"starters": starters, "mains": mains, "drink": drink},
        products,
        options,
    )


def pick(*options, quantity=1):
    return [{"option_id": str(option.id), "quantity": quantity} for option in options]


# split_amount


@pytest.mark.parametrize(
    ("total", "weights", "shares"),
    [
        # The old module's golden vector: 6,00 € over a 4,50 € sandwich and a 2,00 € beer.
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


# combo.combo.list (COMBO-F01)


def test_the_list_by_order_then_name_with_what_the_table_shows():
    second = make_combo("Kids menu", price=800, sort_order=2)
    first = make_combo("Menu of the day", price=1350, sort_order=1)
    make_group(first, "Starters")
    page = run("combo.combo.list", {}, ctx_for("hub_employee"))
    assert [row.id for row in page.rows] == [first.id, second.id]
    row = page.rows[0]
    assert (row.name, row.price, row.supply_kind, row.is_active, row.group_count) == (
        "Menu of the day",
        1350,
        "service",
        True,
        1,
    )
    assert row.tax_category_key == FOOD
    assert row.tax_category_name
    assert page.total == 2


def test_the_list_searches_the_name_and_the_kitchen_name_and_filters():
    day = make_combo("Menu of the day", kitchen_name="DAILY")
    pack = make_combo("Sandwich pack", supply_kind="goods", is_active=False)
    assert [r.id for r in run("combo.combo.list", {"search": "daily"}).rows] == [day.id]
    assert [r.id for r in run("combo.combo.list", {"name": "pack"}).rows] == [pack.id]
    assert [r.id for r in run("combo.combo.list", {"supply_kind": "goods"}).rows] == [
        pack.id
    ]
    assert [r.id for r in run("combo.combo.list", {"is_active": True}).rows] == [day.id]


def test_the_list_sorts_by_any_column_and_pages():
    cheap = make_combo("A", price=500)
    dear = make_combo("B", price=1500)
    middle = make_combo("C", price=1000)
    page = run("combo.combo.list", {"sort": "price", "dir": "desc", "limit": 2})
    assert [r.id for r in page.rows] == [dear.id, middle.id]
    assert page.total == 3
    assert [
        r.id
        for r in run(
            "combo.combo.list", {"sort": "price", "offset": 2, "limit": 2}
        ).rows
    ] == [dear.id]
    assert cheap.id in {r.id for r in run("combo.combo.list", {}).rows}


def test_reading_needs_the_view_permission():
    with pytest.raises(PermissionDenied):
        run("combo.combo.list", {}, ctx_for(permissions=set()))


# combo.combo.get (COMBO-F05, F06, F12, F13)


def test_a_menu_with_its_courses_and_choices_in_order():
    combo, groups, products, options = menu_of_the_day()
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert [g.name for g in detail.groups] == ["Starters", "Mains", "Drink"]
    starters = detail.groups[0]
    assert (starters.min_choices, starters.max_choices, starters.allow_repeat) == (
        1,
        1,
        False,
    )
    assert [
        (o.product_name, o.sku, o.catalog_price, o.price_delta, o.status)
        for o in starters.options
    ] == [
        ("Lentils", "LEN", 700, 0, "offered"),
        ("Salad", "SAL", 650, -50, "offered"),
    ]
    assert detail.sellable is True and detail.blockers == []


def test_a_menu_is_named_by_its_name_as_said():
    combo = make_combo("Menu of the day")
    make_combo("Kids menu")
    assert run("combo.combo.get", {"combo": "menu of the DAY"}).id == combo.id
    # Part of the name, when only one menu has it.
    assert run("combo.combo.get", {"combo": "day"}).id == combo.id
    with pytest.raises(Conflict) as caught:
        run("combo.combo.get", {"combo": "menu"})
    assert caught.value.code == "combo.combo_ambiguous"
    assert (
        "Kids menu" in caught.value.message
        and "Menu of the day" in caught.value.message
    )
    with pytest.raises(NotFound) as missing:
        run("combo.combo.get", {"combo": "brunch"})
    assert missing.value.message == "That menu does not exist in this business."


@pytest.mark.parametrize("name", ["combo.combo.get", "combo.combo.resolve"])
def test_a_menu_is_read_with_its_tree_in_as_many_queries_however_big(name):
    # The menu comes with its courses and choices in the read that finds it: one more course or choice
    # is never one more query (nor a second read of the menu, see test_concurrency.py).
    def queries(courses: int, choices: int) -> int:
        combo = make_combo(f"Menu {courses}x{choices}")
        picks = []
        for c in range(courses):
            course = make_group(combo, f"Course {c}", min_choices=1)
            options = [make_option(course, make_product(f"Dish {c}.{n}")) for n in range(choices)]
            picks.append({"option_id": str(options[0].id)})
        data = {"id": str(combo.id)} | ({"choices": picks} if name == "combo.combo.resolve" else {})
        with CaptureQueriesContext(connection) as read:
            run(name, data)
        return len(read)

    assert queries(3, 3) == queries(1, 1)


def test_each_choice_says_whether_it_is_offered():
    combo, groups, products, options = menu_of_the_day()
    options["salad"].is_available = False
    options["salad"].save()
    products["chicken"].is_active = False
    products["chicken"].save()
    products["wine"].is_deleted = True
    products["wine"].save()
    statuses = {
        o.product_name: o.status
        for g in run("combo.combo.get", {"id": str(combo.id)}).groups
        for o in g.options
    }
    assert statuses == {
        "Lentils": "offered",
        "Salad": "sold_out",
        "Hake": "offered",
        "Chicken": "product_inactive",
        "Water": "offered",
        "House wine": "product_deleted",
    }


def test_why_a_menu_is_not_on_the_till():
    combo = make_combo("Menu of the day", is_active=False)
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert detail.sellable is False
    assert [b.code for b in detail.blockers] == [
        "combo.not_on_sale",
        "combo.no_choices",
    ]
    combo.is_active = True
    combo.save()
    starters = make_group(combo, "Starters", min_choices=2, max_choices=2)
    make_option(starters, make_product("Lentils"))
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert [(b.code, b.group_id) for b in detail.blockers] == [
        ("combo.group_short", starters.id)
    ]
    assert (
        detail.blockers[0].message
        == "The course “Starters” has fewer choices on offer than it asks for."
    )
    # Repeating one choice fills a course of two.
    starters.allow_repeat = True
    starters.save()
    assert run("combo.combo.get", {"id": str(combo.id)}).sellable is True


def test_a_menu_eaten_in_whose_tax_category_taxes_deactivated_is_off_the_till():
    combo = make_combo(tax_category=tax_category("e2e.combo_old"))
    make_option(make_group(combo), make_product())
    combo.tax_category.is_active = False
    combo.tax_category.save()
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert [b.code for b in detail.blockers] == ["combo.tax_category_inactive"]


# combo.combo.for_sale (COMBO-F07)


def test_the_till_gets_the_menus_it_can_sell_with_the_choices_on_offer():
    combo, groups, products, options = menu_of_the_day()
    options["salad"].is_available = False
    options["salad"].save()
    dessert = make_group(combo, "Dessert", min_choices=0, max_choices=1)
    make_option(dessert, make_product("Flan", is_active=False))
    make_combo("Withdrawn", is_active=False)
    incomplete = make_combo("Incomplete")
    make_group(incomplete, "Starters")
    page = run("combo.combo.for_sale", {}, ctx_for("hub_employee"))
    assert [row.name for row in page.rows] == ["Menu of the day"]
    assert page.total == 1
    row = page.rows[0]
    assert (row.price, row.supply_kind, row.kitchen_name) == (1350, "service", "MENU")
    # The optional dessert has nothing on offer: it is left out.
    assert [g.name for g in row.groups] == ["Starters", "Mains", "Drink"]
    assert [(o.product_name, o.price_delta) for o in row.groups[0].options] == [
        ("Lentils", 0)
    ]
    assert [(o.product_name, o.price_delta) for o in row.groups[1].options] == [
        ("Hake", 200),
        ("Chicken", 0),
    ]


def test_the_till_searches_and_pages_the_menus():
    for name in ("Menu A", "Menu B", "Kids"):
        make_option(make_group(make_combo(name)), make_product(f"Dish {name}"))
    assert [
        r.name for r in run("combo.combo.for_sale", {"search": "menu", "limit": 1}).rows
    ] == ["Menu A"]
    assert run("combo.combo.for_sale", {"search": "menu", "limit": 1}).total == 2


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


def refusal(combo, choices, **extra) -> Conflict:
    with pytest.raises(Conflict) as caught:
        run("combo.combo.resolve", {"id": str(combo.id), "choices": choices, **extra})
    return caught.value


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


# Eaten in or to take away: the menu's setting, unless Ventas says how this line is sold (review 1)


def sandwich_and_beer(supply_kind="goods", **fields):
    combo = make_combo("Sandwich pack", price=600, supply_kind=supply_kind, **fields)
    make_option(make_group(combo, "Sandwich"), make_product("Ham sandwich", price=450, tax=FOOD))
    make_option(make_group(combo, "Drink"), make_product("Beer", price=200, tax=ALCOHOL))
    return combo


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


def test_the_takeaway_map_is_explicit():
    from apps.combo.queries import TAKEAWAY_CATEGORY

    assert TAKEAWAY_CATEGORY == {"restaurant.alcohol": "retail.alcohol"}


# An open check is charged at what was ordered, even if a dish ran out since (review 2)


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


# What the till cannot charge is not offered (review 4, 9)


def statuses(combo) -> dict[str, str]:
    detail = run("combo.combo.get", {"id": str(combo.id)})
    return {o.product_name: o.status for g in detail.groups for o in g.options}


def test_to_take_away_a_dish_without_a_rate_to_bill_it_is_not_offered():
    combo = sandwich_and_beer()
    make_option(make_group(combo, "Extra"), make_product("Mystery box", tax=None))
    assert statuses(combo)["Mystery box"] == "untaxed"
    # Eaten in, the menu's own category bills it.
    eaten_in = make_combo("Menu")
    make_option(make_group(eaten_in), make_product("Mystery bag", tax=None))
    assert statuses(eaten_in)["Mystery bag"] == "offered"


def test_to_take_away_a_beer_without_its_retail_category_is_not_offered():
    retail = tax_category(ALCOHOL_TO_GO)
    retail.is_active = False
    retail.save()
    combo = sandwich_and_beer()
    assert statuses(combo)["Beer"] == "untaxed"
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert [b.code for b in detail.blockers] == ["combo.group_short"]


def test_a_pack_whose_dishes_all_cost_nothing_at_different_rates_is_off_the_till():
    combo = make_combo("Free pack", price=600, supply_kind="goods")
    make_option(make_group(combo, "A"), make_product("Free A", price=0, tax=FOOD))
    make_option(make_group(combo, "B"), make_product("Free B", price=0, tax=ALCOHOL))
    detail = run("combo.combo.get", {"id": str(combo.id)})
    assert [b.code for b in detail.blockers] == ["combo.no_catalog_price"]
    assert run("combo.combo.for_sale", {}).total == 0


def test_a_dish_now_sold_by_weight_is_not_offered_nor_charged():
    combo, groups, products, options = menu_of_the_day()
    products["hake"].unit = "kg"
    products["hake"].pricing_unit = "kg"
    products["hake"].save()
    assert statuses(combo)["Hake"] == "not_by_unit"
    for extra in ({}, {"amount": 1350}):
        error = refusal(combo, pick(options["lentils"], options["hake"], options["water"]), **extra)
        assert error.code == "combo.product_not_by_unit"
