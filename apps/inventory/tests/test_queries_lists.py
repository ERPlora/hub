"""What every list of the inventory app shares: a tie goes by id in the list's own direction, and every list
searches."""

from decimal import Decimal

import pytest

from apps.inventory.models import Category
from apps.inventory.schemas.categories import CategoryListIn
from apps.inventory.schemas.movements import MovementListIn
from apps.inventory.schemas.product_categories import ProductCategoryListIn
from apps.inventory.schemas.products import ForSaleListIn, ProductListIn
from apps.inventory.schemas.stock import LowStockListIn
from apps.inventory.schemas.units import UnitListIn
from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, link, movement, names, product, run

pytestmark = HUB_DB


def _tied_products():
    return [product(f"Item {n}", stock=Decimal("5")).id for n in range(4)]


def _tied_low_stock():
    return [
        product(f"Item {n}", stock=Decimal("1"), low_stock_threshold=Decimal("2")).id
        for n in range(4)
    ]


def _tied_categories():
    return [Category.objects.create(name=f"Group {n}", color="#ff0000").id for n in range(4)]


def _tied_movements():
    item = product("Item")
    return [movement(item, "sale", Decimal("1"), Decimal("4")).id for _ in range(4)]


@pytest.mark.parametrize(
    ("operation", "schema", "tied", "column"),
    [
        ("inventory.product.list", ProductListIn, _tied_products, "stock"),
        ("inventory.product.list_low_stock", LowStockListIn, _tied_low_stock, "stock"),
        ("inventory.category.list", CategoryListIn, _tied_categories, "color"),
        ("inventory.movement.list", MovementListIn, _tied_movements, "qty"),
    ],
)
def test_ties_go_by_id_in_the_lists_own_direction(operation, schema, tied, column):
    """As in Customers, a descending list is the ascending one read backwards, ties included, and its pages neither
    repeat nor lose rows."""
    assert_reads_backwards(listed_with(run, operation, column, schema=schema), sorted(tied()))


def test_every_list_searches():
    drinks = Category.objects.create(name="Drinks")
    coffee = product("Coffee", "CAF")
    link(coffee, drinks)
    link(product("Bread", "BRE"), Category.objects.create(name="Food"))

    assert names(run("inventory.product.list_for_sale", ForSaleListIn(search="caf"))) == ["Coffee"]
    assert [row.code for row in run("inventory.unit.list", UnitListIn(search="kilo")).rows] == ["kg"]
    assert [row.code for row in run("inventory.unit.list", UnitListIn(search="ml")).rows] == ["ml"]
    assert [row.product_id for row in run("inventory.product_category.list", ProductCategoryListIn(search="drin")).rows] == [coffee.id]
    assert [row.product_id for row in run("inventory.product_category.list", ProductCategoryListIn(search="caf")).rows] == [coffee.id]
