"""Erasing a customer's personal data from the carts and the orders (CART_CHECKOUT-F14)."""

import pytest
from live.errors import PermissionDenied

from apps.cart_checkout.models import Cart, Order

from .conftest import EARLIER, HUB_DB, events, make_cart, make_order, payload, run

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


# ── Personal data (CART_CHECKOUT-F14) ─────────────────────────────────────────────────────────


@pytest.fixture
def ana_and_bea():
    """Ana's carts (one live, one deleted) and orders, and Bea's, which must stay as they are."""
    live = make_cart(
        "sess_ana", customer_email="ana@example.com", customer_name="Ana García", notes="Call her", abandon_reason="x"
    )
    gone = make_cart("sess_ana_old", customer_email="ANA@example.com", customer_name="Ana", deleted_at=EARLIER)
    personal = {
        "shipping_address": {"line1": "Calle Mayor 1"},
        "billing_address": {"line1": "Calle Mayor 1"},
        "notes": "Leave it at the door",
        "failure_reason": "Card of Ana declined",
    }
    by_email = make_order(make_cart("sess_other", customer_email="other@example.com"), customer_email="ana@example.com", **personal)
    by_cart = make_order(live, order_number="OS-20261014-0002", customer_email="ana.work@example.com", **personal)
    bea = make_cart("sess_bea", customer_email="bea@example.com", customer_name="Bea", notes="Keep")
    bea_order = make_order(bea, order_number="OS-20261014-0003", customer_email="bea@example.com", notes="Keep")
    return {"live": live, "gone": gone, "by_email": by_email, "by_cart": by_cart, "bea": bea, "bea_order": bea_order}


def test_erasing_a_customer_empties_their_personal_data_in_carts_and_orders(ana_and_bea):
    result = run("cart_checkout.customer.erase", {"email": "Ana@Example.com"}, actor="Bea")
    assert (result.carts, result.orders) == (2, 2)
    for cart in (ana_and_bea["live"], ana_and_bea["gone"]):
        row = Cart.objects.get(pk=cart.pk)
        assert (row.customer_email, row.customer_name, row.notes, row.abandon_reason) == ("", "", "", ""), cart
    for order in (ana_and_bea["by_email"], ana_and_bea["by_cart"]):
        row = Order.objects.get(pk=order.pk)
        assert (row.customer_email, row.shipping_address, row.billing_address, row.notes, row.failure_reason) == (
            "",
            {},
            {},
            "",
            "",
        ), order
    # The orders' numbers, totals and statuses stay: they are not personal data.
    assert Order.objects.get(pk=ana_and_bea["by_cart"].pk).total_amount == 2500
    # Nobody else is touched.
    bea = Cart.objects.get(pk=ana_and_bea["bea"].pk)
    assert (bea.customer_email, bea.customer_name, bea.notes) == ("bea@example.com", "Bea", "Keep")
    assert Order.objects.get(pk=ana_and_bea["bea_order"].pk).notes == "Keep"
    assert Cart.objects.get(pk=ana_and_bea["live"].pk).updated_by == "Bea"
    # The event says how many, never whose.
    assert events() == ["cart_checkout.customer.erased"]
    assert payload("cart_checkout.customer.erased") == {"carts": 2, "orders": 2}


def test_erasing_an_email_nobody_has_changes_nothing(ana_and_bea):
    result = run("cart_checkout.customer.erase", {"email": "nobody@example.com"})
    assert (result.carts, result.orders) == (0, 0)
    assert events() == []


def test_erasing_needs_the_manage_permission(ana_and_bea):
    with pytest.raises(PermissionDenied):
        run("cart_checkout.customer.erase", {"email": "ana@example.com"}, role="hub_employee")
    assert Cart.objects.get(pk=ana_and_bea["live"].pk).customer_email == "ana@example.com"
