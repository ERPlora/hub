"""The two category lists (``apps/inventory/queries/categories.py``): the categories with how many products each
has, and the till's map of which product is in which category."""

import uuid

import pytest

from apps.inventory.models import Category
from apps.inventory.schemas.categories import CategoryListIn
from apps.inventory.schemas.product_categories import ProductCategoryListIn

from .conftest import HUB_DB, link, product, run

pytestmark = HUB_DB


# inventory.product_category.list


def test_the_category_map_of_the_till_has_only_active_live_products_and_live_categories():
    drinks, gone = (
        Category.objects.create(name="Drinks"),
        Category.objects.create(name="Gone", is_deleted=True),
    )
    coffee, off = product("Coffee"), product("Off", is_active=False)
    link(coffee, drinks)
    link(coffee, gone)
    link(off, drinks)

    page = run(
        "inventory.product_category.list", ProductCategoryListIn(), role="hub_employee"
    )

    assert [(row.product_id, row.category_id) for row in page.rows] == [
        (coffee.id, drinks.id)
    ]
    assert (
        run(
            "inventory.product_category.list",
            ProductCategoryListIn(category_id=gone.id),
        ).total
        == 0
    )


# inventory.category.list


def test_categories_with_how_many_active_products_each_has(general):
    drinks = Category.objects.create(
        name="Drinks", slug="drinks", tax_category=general, color="#3880ff", order=2
    )
    food = Category.objects.create(name="Food", slug="food")
    Category.objects.create(name="Gone", is_deleted=True)
    for name, active in (("Coffee", True), ("Tea", True), ("Off", False)):
        link(product(name, is_active=active), drinks)
    link(product("Deleted", is_deleted=True, is_active=False), drinks)

    page = run("inventory.category.list", CategoryListIn(), role="hub_employee")

    assert [(row.name, row.product_count) for row in page.rows] == [
        ("Drinks", 2),
        ("Food", 0),
    ]
    assert page.rows[0].model_dump() == {
        "id": drinks.id,
        "name": "Drinks",
        "slug": "drinks",
        "description": "",
        "icon": "ion:cube-outline",
        "color": "#3880ff",
        "order": 2,
        "tax_category_id": general.id,
        "tax_category_key": "product.general",
        "product_count": 2,
    }
    assert [
        row.id
        for row in run("inventory.category.list", CategoryListIn(search="foo")).rows
    ] == [food.id]


def test_a_category_counts_what_the_till_shows_sold_out_included(general):
    drinks = Category.objects.create(name="Drinks")
    for name, sold_out in (("Coffee", False), ("Tea", True)):
        link(product(name, tax=general, is_sold_out=sold_out), drinks)
    [row] = run("inventory.category.list", CategoryListIn()).rows
    # The till's category strip shows this count next to a grid with both tiles, the tea greyed «Sold out»
    # (SALE-F07): the count says what the person sees.
    assert (row.name, row.product_count) == ("Drinks", 2)


def test_category_list_filters_and_orders():
    drinks = Category.objects.create(name="Drinks", slug="drinks", icon="ion:wine", color="#ff0000")
    Category.objects.create(name="Food", slug="food", icon="ion:pizza", color="#00ff00")
    for name in ("Coffee", "Tea"):
        link(product(name), drinks)

    def listed(**params):
        return [row.name for row in run("inventory.category.list", CategoryListIn(**params)).rows]

    assert listed(name="dri") == ["Drinks"]
    assert listed(slug="foo") == ["Food"]
    assert listed(icon="ion:pizza") == ["Food"]
    assert listed(color="#ff0000") == ["Drinks"]
    assert listed(product_count_min=1) == ["Drinks"]
    assert listed(product_count_max=0) == ["Food"]
    assert listed(sort="-product_count") == ["Drinks", "Food"]
    assert listed(sort="-name") == ["Food", "Drinks"]


def test_category_list_names_the_categories_asked_by_id():
    # The product form names the categories of a product beyond the first page.
    drinks = Category.objects.create(name="Drinks", slug="drinks")
    food = Category.objects.create(name="Food", slug="food")
    Category.objects.create(name="Wines", slug="wines")
    gone = Category.objects.create(name="Old", slug="old", is_deleted=True)

    def listed(**params):
        return [row.name for row in run("inventory.category.list", CategoryListIn(**params)).rows]

    assert listed(ids=[food.id, drinks.id]) == ["Drinks", "Food"]
    assert listed(ids=[gone.id]) == []
    assert listed(ids=[uuid.uuid7()]) == []
    assert listed() == ["Drinks", "Food", "Wines"]


def test_category_list_asks_at_most_a_page_of_ids():
    with pytest.raises(ValueError):
        CategoryListIn(ids=[uuid.uuid7() for _ in range(101)])
