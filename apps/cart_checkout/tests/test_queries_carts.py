"""The carts' list (newest first, its search, filters, ranges and sort) and one cart with its lines."""

from decimal import Decimal

import pytest

from .conftest import HUB_DB, NOW, make_item, run, tokens

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


def test_the_carts_newest_first_without_the_deleted_ones(shop):
    page = run("cart_checkout.cart.list")
    assert tokens(page) == ["anon_2", "anon_1", "sess_bea", "sess_ana"]
    assert (page.total, page.limit, page.offset) == (4, 50, 0)


@pytest.mark.parametrize(
    ("typed", "found"),
    [("SESS_", ["sess_bea", "sess_ana"]), ("bea@", ["sess_bea"]), ("garcía", ["sess_ana"]), ("nobody", [])],
)
def test_the_search_reads_the_code_the_email_and_the_name(shop, typed, found):
    # The old screen said «Search session or email…» but its query never read the session code.
    assert tokens(run("cart_checkout.cart.list", {"search": typed})) == found


def test_the_text_filters_narrow_by_fragment(shop):
    assert tokens(run("cart_checkout.cart.list", {"session_token": "anon"})) == ["anon_2", "anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"customer_email": "EXAMPLE"})) == ["sess_bea", "sess_ana"]
    assert tokens(run("cart_checkout.cart.list", {"customer_name": "lópez"})) == ["sess_bea"]
    assert tokens(run("cart_checkout.cart.list", {"notes": "vip"})) == ["sess_ana"]
    assert tokens(run("cart_checkout.cart.list", {"currency": "usd"})) == ["sess_bea"]


def test_the_ranges_include_both_ends(shop):
    assert tokens(run("cart_checkout.cart.list", {"total_amount_min": 900, "total_amount_max": 2500})) == [
        "sess_bea",
        "sess_ana",
    ]
    assert tokens(run("cart_checkout.cart.list", {"total_items_min": "0.5", "total_items_max": "1"})) == [
        "anon_1",
        "sess_bea",
    ]
    created = shop["bea"].created_at
    assert tokens(run("cart_checkout.cart.list", {"created_from": created, "created_to": created})) == ["sess_bea"]
    assert tokens(run("cart_checkout.cart.list", {"expires_to": NOW})) == ["anon_1"]
    assert tokens(run("cart_checkout.cart.list", {"expires_from": NOW})) == ["anon_2"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("total_amount", ["anon_2", "anon_1", "sess_bea", "sess_ana"]),
        ("-total_amount", ["sess_ana", "sess_bea", "anon_1", "anon_2"]),
        ("session_token", ["anon_1", "anon_2", "sess_ana", "sess_bea"]),
        ("created_at", ["sess_ana", "sess_bea", "anon_1", "anon_2"]),
    ],
)
def test_the_order_of_a_column(shop, sort, expected):
    assert tokens(run("cart_checkout.cart.list", {"sort": sort})) == expected


def test_a_cart_with_its_lines_by_its_code(shop):
    first = make_item(shop["ana"], product_ref="p-1", product_name="Champú")
    second = make_item(shop["ana"], product_ref="p-2", product_name="Tinte", quantity=Decimal("0.5"), unit_price=1200)
    cart = run("cart_checkout.cart.get", {"session_token": "sess_ana"})
    assert (cart.id, cart.status) == (shop["ana"].id, "active")
    assert [item.id for item in cart.items] == [first.id, second.id]
    assert cart.items[1].line_total == 600
