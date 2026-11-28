"""The lines of a cart (as they were added, their search, filters and sort) and one line, never of a deleted
cart."""

from decimal import Decimal

import pytest
from live.errors import NotFound

from apps.cart_checkout.models import Cart

from .conftest import HUB_DB, make_item, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


@pytest.fixture
def lines(shop):
    cart = shop["ana"]
    return [
        make_item(cart, product_ref="p-1", product_name="Champú", sku="SH-1", quantity=Decimal("2"), unit_price=1250),
        make_item(cart, product_ref="p-2", product_name="Tinte rubio", sku="TI-9", quantity=Decimal("1"), unit_price=900),
        make_item(cart, product_ref="p-3", product_name="Peine", quantity=Decimal("0.5"), unit_price=200),
        make_item(shop["bea"], product_ref="p-1", product_name="Champú"),
    ]


def names(page) -> list[str]:
    return [row.product_name for row in page.rows]


def test_the_lines_of_a_cart_as_they_were_added(lines):
    page = run("cart_checkout.item.list", {"session_token": "sess_ana"})
    assert names(page) == ["Champú", "Tinte rubio", "Peine"]
    assert page.total == 3
    assert names(run("cart_checkout.item.list", {"cart_id": str(lines[3].cart_id)})) == ["Champú"]


def test_the_lines_search_filter_and_sort(lines):
    ana = {"session_token": "sess_ana"}
    assert names(run("cart_checkout.item.list", ana | {"search": "ti-9"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"product_ref": "p-3"})) == ["Peine"]
    assert names(run("cart_checkout.item.list", ana | {"product_name": "TINTE"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"sku": "sh"})) == ["Champú"]
    assert names(run("cart_checkout.item.list", ana | {"quantity_min": "1", "quantity_max": "1"})) == ["Tinte rubio"]
    assert names(run("cart_checkout.item.list", ana | {"unit_price_max": 900})) == ["Tinte rubio", "Peine"]
    assert names(run("cart_checkout.item.list", ana | {"line_total_min": 2500})) == ["Champú"]
    assert names(run("cart_checkout.item.list", ana | {"sort": "-line_total"})) == ["Champú", "Tinte rubio", "Peine"]


def test_the_lines_of_an_unknown_cart_are_not_found(lines):
    with pytest.raises(NotFound):
        run("cart_checkout.item.list", {"session_token": "nope"})


def test_one_line_by_its_id(lines):
    item = run("cart_checkout.item.get", {"item_id": str(lines[1].id)})
    assert (item.product_name, item.unit_price, item.cart_id) == ("Tinte rubio", 900, lines[1].cart_id)
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.get", {"item_id": "0199e2a0-0000-7000-8000-000000000000"})
    assert caught.value.code == "cart_checkout.item_not_found"


def test_the_lines_of_a_deleted_cart_are_gone_with_it(shop):
    # CART_CHECKOUT-F06: a deleted cart's lines stay in the database for its orders,
    # but nobody reads them any more, neither the cart's list nor one line by its id.
    gone = Cart.objects.get(session_token="sess_gone")
    line = make_item(gone, product_name="Champú")
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.get", {"item_id": str(line.id)})
    assert caught.value.code == "cart_checkout.item_not_found"
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.item.list", {"cart_id": str(gone.id)})
    assert caught.value.code == "cart_checkout.cart_not_found"
