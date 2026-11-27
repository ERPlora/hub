"""The write operations on a cart's lines: adding, changing and removing them (CART_CHECKOUT-F02, F03)."""

from decimal import Decimal

import pytest
from live.errors import Conflict, InvalidPayload, NotFound
from live.models import OutboxEvent

from apps.cart_checkout.models import CartItem

from .conftest import EARLIER, HUB_DB, NOW, add, events, make_cart, make_item, payload, refused, run, stored

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


# ── Lines (CART_CHECKOUT-F02, F03) ────────────────────────────────────────────────────────────


def test_adding_a_line_computes_its_total_and_the_cart_totals():
    cart = make_cart("sess_1")
    result = add("sess_1", quantity="0.5", unit_price=1200, sku="SH-1", variant_attributes={"size": "M"})
    assert result.removed is False
    assert (result.item.quantity, result.item.unit_price, result.item.line_total) == (Decimal("0.5"), 1200, 600)
    assert (result.item.sku, result.item.variant_attributes) == ("SH-1", {"size": "M"})
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("0.5"), 600)
    assert stored(cart).last_activity_at == NOW
    assert events() == ["cart_checkout.item.added"]
    assert payload("cart_checkout.item.added") == {
        "item_id": str(result.item.id),
        "cart_id": str(cart.id),
        "session_token": "sess_1",
        "product_ref": "p-1",
        "quantity": "0.500",
        "line_total": 600,
        "currency": "EUR",
    }


@pytest.mark.parametrize(
    ("quantity", "price", "total"),
    [("2", 1250, 2500), ("0.333", 100, 33), ("0.005", 100, 1), ("0.015", 100, 2), ("3", 0, 0)],
)
def test_a_line_total_is_rounded_to_the_cent_half_up(quantity, price, total):
    make_cart("sess_1")
    assert add("sess_1", quantity=quantity, unit_price=price).item.line_total == total


def test_the_cart_totals_are_the_sum_of_its_lines():
    make_cart("sess_1")
    add("sess_1", quantity="2", unit_price=1250)
    result = add("sess_1", quantity="0.5", unit_price=999, product_ref="p-2")
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("2.5"), 2500 + 500)


def test_a_line_goes_to_the_cart_of_the_customer_named():
    cart = make_cart("sess_1", customer_email="ana@example.com")
    result = run(
        "cart_checkout.item.add",
        {"customer": "ana@example.com", "product_ref": "p", "product_name": "Tinte", "quantity": "1", "unit_price": 900},
    )
    assert result.cart.id == cart.id


def test_a_line_whose_total_is_above_what_a_cart_holds_is_refused_under_quantity():
    # Review (BAJO): 1 000 000 × 99 999 999 999,99 € overflowed the database's bigint (a 500).
    make_cart("sess_1")
    with pytest.raises(InvalidPayload) as caught:
        add("sess_1", quantity="1000000", unit_price=9999999999999)
    refused(caught, "invalid_field")
    assert caught.value.fields == {"quantity": "The total of this line (quantity × price) is above what a cart can hold."}
    assert CartItem.objects.count() == 0


def test_a_cart_whose_total_would_go_above_what_it_holds_takes_no_more_lines():
    cart = make_cart("sess_1", total_amount=9_999_999_999_000)
    make_item(cart, unit_price=9_999_999_999_000, line_total=9_999_999_999_000)
    with pytest.raises(InvalidPayload) as caught:
        add("sess_1", quantity="1", unit_price=1000)
    refused(caught, "invalid_field")
    assert caught.value.fields == {"quantity": "The cart's total would be above what a cart can hold."}


def test_a_new_quantity_whose_total_is_too_large_is_refused_and_the_line_stays():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=9999999999999).item
    OutboxEvent.objects.all().delete()
    with pytest.raises(InvalidPayload) as caught:
        run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "2"})
    refused(caught, "invalid_field")
    assert set(caught.value.fields) == {"quantity"}
    assert CartItem.objects.get(pk=line.id).quantity == Decimal("1")


@pytest.mark.parametrize("status", ["abandoned", "converted", "expired"])
def test_a_cart_that_is_not_active_takes_no_line(status):
    make_cart("sess_1", status=status)
    with pytest.raises(Conflict) as caught:
        add("sess_1")
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.count() == 0


def test_an_overdue_cart_takes_no_line():
    make_cart("sess_1", expires_at=EARLIER)
    with pytest.raises(Conflict) as caught:
        add("sess_1")
    refused(caught, "cart_checkout.cart_not_active")


def test_a_line_for_a_cart_that_does_not_exist_is_refused():
    with pytest.raises(NotFound) as caught:
        add("nope")
    refused(caught, "cart_checkout.cart_not_found")


def test_changing_a_quantity_uses_the_price_kept_on_the_line():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "2"})
    assert (result.item.quantity, result.item.line_total, result.removed) == (Decimal("2"), 700, False)
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("2"), 700)
    assert events() == ["cart_checkout.item.updated"]
    assert payload("cart_checkout.item.updated") == {
        "item_id": str(line.id),
        "cart_id": str(result.cart.id),
        "quantity": "2.000",
        "removed": False,
    }


def test_a_quantity_of_zero_removes_the_line():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    add("sess_1", quantity="1", unit_price=100, product_ref="p-2")
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.update", {"item_id": str(line.id), "quantity": "0"})
    assert (result.item, result.removed) == (None, True)
    assert (result.cart.total_items, result.cart.total_amount) == (Decimal("1"), 100)
    assert not CartItem.objects.filter(pk=line.id).exists()
    assert events() == ["cart_checkout.item.updated"]
    assert payload("cart_checkout.item.updated")["removed"] is True


def test_removing_a_line_recomputes_the_totals():
    make_cart("sess_1")
    line = add("sess_1", quantity="1", unit_price=350).item
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.item.remove", {"item_id": str(line.id)})
    assert (result.item, result.removed, result.cart.total_amount) == (None, True, 0)
    assert events() == ["cart_checkout.item.removed"]
    assert payload("cart_checkout.item.removed") == {"item_id": str(line.id), "cart_id": str(result.cart.id)}


@pytest.mark.parametrize("name", ["cart_checkout.item.update", "cart_checkout.item.remove"])
def test_a_line_that_does_not_exist_is_refused(name):
    data = {"item_id": "0199e2a0-0000-7000-8000-000000000000"}
    if name.endswith("update"):
        data["quantity"] = "1"
    with pytest.raises(NotFound) as caught:
        run(name, data)
    refused(caught, "cart_checkout.item_not_found")


@pytest.mark.parametrize("name", ["cart_checkout.item.update", "cart_checkout.item.remove"])
def test_the_lines_of_a_cart_that_is_not_active_do_not_change(name):
    cart = make_cart("sess_1", status="converted")
    line = make_item(cart, quantity=Decimal("1"), unit_price=100)
    data = {"item_id": str(line.id)}
    if name.endswith("update"):
        data["quantity"] = "3"
    with pytest.raises(Conflict) as caught:
        run(name, data)
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.get(pk=line.pk).quantity == Decimal("1")
