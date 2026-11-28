"""The orders' list (newest first, its search, filters and sort) and one order by its number or its id."""

import pytest
from live.errors import NotFound

from .conftest import EARLIER, HUB_DB, NOW, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


def numbers(page) -> list[str]:
    return [row.order_number for row in page.rows]


def test_the_orders_newest_first(orders):
    page = run("cart_checkout.order.list")
    assert numbers(page) == ["OS-20261014-0002", "OS-20261014-0001", "OS-20261013-0001"]
    assert page.total == 3


@pytest.mark.parametrize(
    ("typed", "found"),
    [("0002", ["OS-20261014-0002"]), ("BEA@", ["OS-20261014-0001"]), ("20261013", ["OS-20261013-0001"])],
)
def test_the_order_search_reads_the_number_and_the_email(orders, typed, found):
    assert numbers(run("cart_checkout.order.list", {"search": typed})) == found


def test_the_order_filters(orders, shop):
    def find(**params):
        return numbers(run("cart_checkout.order.list", params))

    assert find(status="paid") == ["OS-20261014-0001"]
    assert find(cart_id=str(shop["ana"].id)) == ["OS-20261014-0002", "OS-20261013-0001"]
    assert find(customer_email="ana@") == ["OS-20261014-0002", "OS-20261013-0001"]
    assert find(payment_method="trans") == ["OS-20261014-0001"]
    assert find(shipping_method="Courier") == ["OS-20261014-0002"]
    assert find(currency="usd") == ["OS-20261014-0001"]
    assert find(total_amount_min=300, total_amount_max=900) == ["OS-20261014-0002", "OS-20261014-0001"]
    assert find(placed_from=EARLIER, placed_to=NOW) == ["OS-20261014-0002", "OS-20261014-0001"]
    assert find(paid_to=EARLIER) == ["OS-20261013-0001"]


def test_the_orders_sort_by_a_column(orders):
    assert numbers(run("cart_checkout.order.list", {"sort": "total_amount"})) == [
        "OS-20261014-0002",
        "OS-20261014-0001",
        "OS-20261013-0001",
    ]
    assert numbers(run("cart_checkout.order.list", {"sort": "order_number"}))[0] == "OS-20261013-0001"


def test_an_order_by_its_number_or_its_id(orders):
    assert run("cart_checkout.order.get", {"order_number": "os-20261014-0002"}).id == orders[2].id
    whole = run("cart_checkout.order.get", {"order_id": str(orders[0].id)})
    assert (whole.order_number, whole.payment_method, whole.status) == ("OS-20261013-0001", "Card", "completed")
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.order.get", {"order_number": "OS-20991231-0001"})
    assert caught.value.code == "cart_checkout.order_not_found"
