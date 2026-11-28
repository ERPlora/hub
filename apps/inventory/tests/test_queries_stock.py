"""The stock panel (``apps/inventory/queries/stock.py``): how many tracked articles are in, out or low, and what
the stock is worth at cost."""

from decimal import Decimal

from apps.inventory.schemas.stock import SummaryIn

from .conftest import HUB_DB, product, run

pytestmark = HUB_DB


def test_the_panel_counts_tracked_articles_and_values_them_at_cost():
    threshold = {"low_stock_threshold": Decimal("5")}
    product("A", cost=200, stock=Decimal("10"), **threshold)  # in stock, valued
    product("B", cost=300, stock=Decimal("0"), **threshold)  # out
    product("C", cost=0, stock=Decimal("2"), **threshold)  # in stock, low, no cost
    product(
        "D", cost=400, stock=Decimal("-3"), **threshold
    )  # oversold: out and low, never subtracts
    product("S", cost=100, stock=Decimal("3"), product_type="service", **threshold)
    product(
        "K", cost=150, stock=Decimal("0.5"), unit="kg", **threshold
    )  # half a kilo: 75 cents
    product("U", cost=999, stock=Decimal("50"), track_stock=False)
    product("I", cost=999, stock=Decimal("50"), is_active=False)

    summary = run("inventory.stock.get_summary", SummaryIn(), role="hub_manager")

    assert summary.model_dump() == {
        "products_tracked": 5,
        "products_in_stock": 3,
        "products_out_of_stock": 2,
        "products_low_stock": 4,
        "products_without_cost": 1,
        "stock_value": 200 * 10 + 75,
        "active_products": 7,
    }


def test_the_value_rounds_half_up_to_the_cent():
    product("Saffron", cost=3, stock=Decimal("0.5"), unit="kg")  # 1.5 cents
    assert run("inventory.stock.get_summary", SummaryIn()).stock_value == 2


def test_an_empty_panel():
    assert set(
        run("inventory.stock.get_summary", SummaryIn()).model_dump().values()
    ) == {0}
