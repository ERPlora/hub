"""How a cart and an order read in the operations that give one: every field a cart says, an order's cart code and
its currency."""

from decimal import Decimal

import pytest

from .conftest import HUB_DB, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("clock")]


def test_a_row_carries_everything_a_cart_says(shop):
    row = run("cart_checkout.cart.list", {"session_token": "sess_ana"}).rows[0]
    assert row.model_dump() == {
        "id": shop["ana"].id,
        "session_token": "sess_ana",
        "customer_email": "ana@example.com",
        "customer_name": "Ana García",
        "status": "active",
        "total_items": Decimal("2.000"),
        "total_amount": 2500,
        "currency": "EUR",
        "currency_decimals": 2,
        "expires_at": None,
        "last_activity_at": None,
        "notes": "VIP",
        "abandon_reason": "",
        "created_by": "",
        "updated_by": "",
        "created_at": shop["ana"].created_at,
        "updated_at": shop["ana"].updated_at,
    }


def test_an_order_row_says_its_cart_code_and_its_currency(orders):
    row = run("cart_checkout.order.list", {"order_number": "20261014-0001"}).rows[0]
    assert (row.session_token, row.currency, row.total_amount, row.status) == ("sess_bea", "USD", 900, "paid")
