"""The list of menus and one menu with its courses and choices (COMBO-F01, F05, F06, F12)."""

import pytest
from live.errors import PermissionDenied

from apps.combo.queries.menus import list_combos
from apps.combo.schemas.menus import ComboListIn
from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import FOOD, HUB_DB, ctx_for, make_combo, make_group, menu_of_the_day, run

pytestmark = HUB_DB


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


@pytest.mark.parametrize("column", ["price", "sort_order", "is_active", "supply_kind"])
def test_ties_read_backwards_in_a_descending_list(column):
    """hub#768, as in Customers: a descending list is the ascending one read backwards, ties included, and its pages
    neither repeat nor lose rows."""
    menus = [make_combo("Menu A"), make_combo("Menu A"), make_combo("Menu B"), make_combo("Menu B")]
    expected = sorted(menus, key=lambda menu: (menu.name, menu.id))
    assert_reads_backwards(listed_with(run, "combo.combo.list", column, by_dir=True), [menu.id for menu in expected])


def test_reading_needs_the_view_permission():
    with pytest.raises(PermissionDenied):
        run("combo.combo.list", {}, ctx_for(permissions=set()))


def test_the_name_filter_does_not_read_the_kitchen_name():
    make_combo("Menu of the day", kitchen_name="DAILY")
    assert list_combos(ctx_for(), ComboListIn(name="daily")).rows == []


# combo.combo.get (COMBO-F05, F06, F12)


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
