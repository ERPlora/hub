"""What can be sold (COMBO-F05, F06, F07, F12, F13): whether a choice is offered, and why a menu is not on the till."""

import pytest

from apps.combo.queries.offers import sold_by_unit

from .conftest import (
    ALCOHOL,
    ALCOHOL_TO_GO,
    FOOD,
    HUB_DB,
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


# What the till cannot charge is not offered


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


@pytest.mark.parametrize(("quantity", "portion"), [(1, True), (6, False)])
def test_a_portion_is_priced_one_by_one(quantity, portion):
    assert sold_by_unit(make_product("Croquettes", price_quantity=quantity)) is portion
