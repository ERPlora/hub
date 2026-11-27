"""The carts' write operations: creating one, how a cart is named, abandoning, deleting, clearing and expiring
them (CART_CHECKOUT-F01, F04 to F07)."""

from decimal import Decimal

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.cart_checkout.models import Cart, CartItem, Order
from apps.sale.tests.test_business_currency import business_in

from .conftest import (
    EARLIER,
    HUB_DB,
    LATER,
    NOW,
    add,
    events,
    make_cart,
    make_item,
    make_order,
    payload,
    refused,
    run,
    stored,
)

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


# ── Create (CART_CHECKOUT-F01) ────────────────────────────────────────────────────────────────


def test_creating_a_cart_in_the_business_currency():
    cart = run(
        "cart_checkout.cart.create",
        {"session_token": "sess_1", "customer_email": "ana@example.com", "customer_name": "Ana García"},
        actor="Ana",
    )
    assert (cart.session_token, cart.status, cart.currency) == ("sess_1", "active", "EUR")
    assert (cart.total_items, cart.total_amount) == (Decimal("0"), 0)
    assert (cart.customer_email, cart.customer_name) == ("ana@example.com", "Ana García")
    row = Cart.objects.get(pk=cart.id)
    assert (row.created_by, row.updated_by, row.last_activity_at) == ("Ana", "Ana", NOW)
    assert events() == ["cart_checkout.cart.created"]
    assert payload("cart_checkout.cart.created") == {
        "id": str(cart.id),
        "session_token": "sess_1",
        "currency": "EUR",
    }


@pytest.mark.parametrize(("currency", "expected"), [("usd", "USD"), (None, "EUR"), ("", "EUR")])
def test_an_explicit_currency_wins_and_an_empty_one_is_the_business_one(currency, expected):
    # The old cart_currency batteries: a cart without a currency is born in the business's one.
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "currency": currency})
    assert cart.currency == expected


def test_a_cart_without_a_currency_takes_the_business_one_never_a_literal_euro():
    # A hub that does not work in euros got euro carts from the screen, the
    # assistant and the API. The cart follows the business's country (test_business_currency.py).
    business_in("GB")
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    assert cart.currency == "GBP"
    assert payload("cart_checkout.cart.created")["currency"] == "GBP"


def test_a_cart_can_carry_its_expiry():
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "expires_at": LATER.isoformat()})
    assert cart.expires_at == LATER


def test_a_session_code_in_use_is_refused_under_its_field():
    make_cart("sess_1")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.create", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.session_taken")
    assert caught.value.fields == {"session_token": "There is already a cart with that session."}
    assert Cart.objects.count() == 1


def test_a_deleted_cart_frees_its_session_code():
    make_cart("sess_1", deleted_at=EARLIER)
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1"})
    assert Cart.objects.filter(session_token="sess_1").count() == 2
    assert cart.status == "active"


def test_an_employee_only_looks():
    with pytest.raises(PermissionDenied):
        run("cart_checkout.cart.create", {"session_token": "sess_1"}, role="hub_employee")
    assert Cart.objects.count() == 0


# ── How a cart is named ───────────────────────────────────────────────────────────────────────


def test_a_cart_is_found_by_its_id_its_code_or_its_customer():
    cart = make_cart("sess_1", customer_email="ana@example.com", customer_name="Ana García")
    make_cart("sess_2", customer_email="bea@example.com", customer_name="Bea López")
    for said in (
        {"cart_id": str(cart.id)},
        {"session_token": "sess_1"},
        {"customer": "ANA@example.com"},
        {"customer": "garcía"},
    ):
        result = run("cart_checkout.cart.mark_abandoned", said)
        assert result.id == cart.id, said
        Cart.objects.filter(pk=cart.pk).update(status="active")


def test_a_customer_with_several_carts_asks_which_one():
    make_cart("sess_1", customer_name="Ana García")
    make_cart("sess_2", customer_name="Ana Pérez")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"customer": "ana"})
    refused(caught, "cart_checkout.cart_ambiguous")
    assert caught.value.message == "“ana” matches several carts: sess_1, sess_2. Say which one."


def test_a_cart_that_does_not_exist_or_was_deleted_is_not_found():
    make_cart("gone", deleted_at=EARLIER)
    for said in ({"session_token": "nope"}, {"session_token": "gone"}, {"customer": "nobody"}):
        with pytest.raises(NotFound) as caught:
            run("cart_checkout.cart.mark_abandoned", said)
        assert caught.value.code == "cart_checkout.cart_not_found", said
    assert events() == []


# ── Abandon (CART_CHECKOUT-F05) ───────────────────────────────────────────────────────────────


def test_abandoning_an_active_cart_keeps_its_lines_and_its_reason():
    cart = make_cart("sess_1")
    make_item(cart)
    result = run(
        "cart_checkout.cart.mark_abandoned", {"session_token": "sess_1", "reason": "Left the shop"}, actor="Bea"
    )
    assert (result.status, result.abandon_reason) == ("abandoned", "Left the shop")
    assert stored(cart).updated_by == "Bea"
    assert CartItem.objects.filter(cart=cart).count() == 1
    assert events() == ["cart_checkout.cart.abandoned"]
    assert payload("cart_checkout.cart.abandoned") == {"id": str(cart.id), "session_token": "sess_1"}


@pytest.mark.parametrize("status", ["abandoned", "converted", "expired"])
def test_only_an_active_cart_is_abandoned(status):
    make_cart("sess_1", status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    label = {"abandoned": "Abandoned", "converted": "Converted", "expired": "Expired"}[status]
    assert caught.value.message == f"This cart no longer takes changes: it is {label}."


def test_an_active_cart_past_its_expiry_is_already_expired():
    make_cart("sess_1", expires_at=EARLIER)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.mark_abandoned", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    assert caught.value.message == "This cart no longer takes changes: it is Expired."


# ── Delete (CART_CHECKOUT-F06) ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["active", "converted"])
def test_deleting_a_cart_in_any_status_keeps_its_orders(status):
    cart = make_cart("sess_1", status=status)
    order = make_order(cart)
    result = run("cart_checkout.cart.delete", {"session_token": "sess_1"})
    assert result.id == cart.id
    assert stored(cart).deleted_at == NOW
    assert Order.objects.filter(pk=order.pk).exists()
    assert events() == ["cart_checkout.cart.deleted"]
    assert payload("cart_checkout.cart.deleted") == {"id": str(cart.id), "session_token": "sess_1"}
    with pytest.raises(NotFound):
        run("cart_checkout.cart.get", {"cart_id": str(cart.id)})


def test_deleting_a_cart_that_is_gone_is_refused():
    make_cart("sess_1", deleted_at=EARLIER)
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.cart.delete", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_found")


# ── Clear (CART_CHECKOUT-F04) ─────────────────────────────────────────────────────────────────


def test_clearing_a_cart_removes_its_lines_and_zeroes_its_totals():
    make_cart("sess_1")
    add("sess_1", quantity="2")
    add("sess_1", quantity="1", unit_price=500)
    OutboxEvent.objects.all().delete()
    result = run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    assert (result.status, result.total_items, result.total_amount) == ("active", Decimal("0"), 0)
    assert CartItem.objects.count() == 0
    assert events() == ["cart_checkout.cart.cleared"]


def test_clearing_an_empty_cart_changes_nothing():
    make_cart("sess_1")
    run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    assert events() == []


def test_only_an_active_cart_is_cleared():
    cart = make_cart("sess_1", status="abandoned")
    make_item(cart)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.cart.clear", {"session_token": "sess_1"})
    refused(caught, "cart_checkout.cart_not_active")
    assert CartItem.objects.count() == 1


# ── Expire (CART_CHECKOUT-F07) ────────────────────────────────────────────────────────────────


def test_expiring_marks_the_overdue_active_carts_and_says_how_many():
    overdue = make_cart("old_1", expires_at=EARLIER)
    make_cart("old_2", expires_at=NOW)  # its expiry is now: expired
    make_cart("future", expires_at=LATER)
    make_cart("forever")
    make_cart("left", status="abandoned", expires_at=EARLIER)
    make_cart("gone", expires_at=EARLIER, deleted_at=EARLIER)
    result = run("cart_checkout.cart.cleanup_expired", {}, actor="*")
    assert result.expired == 2
    assert stored(overdue).status == "expired"
    assert dict(Cart.objects.values_list("session_token", "status")) == {
        "old_1": "expired",
        "old_2": "expired",
        "future": "active",
        "forever": "active",
        "left": "abandoned",
        "gone": "active",
    }
    assert events() == ["cart_checkout.cart.expired"]
    assert payload("cart_checkout.cart.expired") == {"count": 2}


def test_expiring_without_overdue_carts_says_zero_and_records_nothing():
    make_cart("future", expires_at=LATER)
    assert run("cart_checkout.cart.cleanup_expired", {}).expired == 0
    assert events() == []
