"""The menus the till can sell (COMBO-F07)."""

from apps.combo.queries.till import list_for_sale
from apps.combo.schemas.till import ForSaleIn

from .conftest import HUB_DB, ctx_for, make_combo, make_group, make_option, make_product, menu_of_the_day, run

pytestmark = HUB_DB


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


def test_the_till_says_how_many_each_course_takes():
    course = make_group(make_combo(), min_choices=1, max_choices=2, allow_repeat=True)
    make_option(course, make_product())
    [row] = list_for_sale(ctx_for("hub_employee"), ForSaleIn()).rows
    assert [(group.min_choices, group.max_choices, group.allow_repeat) for group in row.groups] == [(1, 2, True)]
