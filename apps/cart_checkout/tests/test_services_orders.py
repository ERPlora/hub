"""The orders' write operations: starting one from a cart with its number of the day, and its steps (paid,
failed, completed) (CART_CHECKOUT-F08 to F11)."""

import datetime as dt

import pytest
from django.utils import translation
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.cart_checkout.models import Cart, Order, OrderCounter

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
)

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


def initiate(token="sess_1", **fields):
    data = {"session_token": token, "customer_email": "ana@example.com"} | fields
    return run("cart_checkout.checkout.initiate", data)


# ── Orders: initiate (CART_CHECKOUT-F08) ──────────────────────────────────────────────────────


def test_the_number_of_an_order_is_of_the_businesss_day(night_elsewhere):
    make_cart("sess_1", currency="EUR")
    add("sess_1", quantity="1", unit_price=1250)
    assert initiate().order_number == "OS-20261102-0001"


def test_a_business_that_changes_zone_never_repeats_an_order_number(across_a_change_of_zone):
    make_cart("sess_1", currency="EUR")
    add("sess_1", quantity="1", unit_price=1250)
    assert [number for number in across_a_change_of_zone(lambda: initiate().order_number)] == [
        "OS-20261102-0001",
        "OS-20261103-0001",
        "OS-20261102-0002",
    ]


def test_initiating_an_order_copies_the_cart_total_with_its_number_of_the_day():
    make_cart("sess_1", currency="USD")
    add("sess_1", quantity="2", unit_price=1250)
    OutboxEvent.objects.all().delete()
    order = initiate(
        shipping_address={"line1": "Calle Mayor 1", "city": "Madrid"},
        shipping_method="Courier",
        payment_method="Card",
        notes="Ring twice",
    )
    assert order.order_number == "OS-20261014-0001"
    assert (order.status, order.total_amount, order.currency) == ("initiated", 2500, "USD")
    assert order.customer_email == "ana@example.com"
    # Without a billing address, the shipping one (the old handler's fallback).
    assert order.billing_address == order.shipping_address == {"line1": "Calle Mayor 1", "city": "Madrid"}
    assert (order.shipping_method, order.payment_method, order.notes) == ("Courier", "Card", "Ring twice")
    assert (order.placed_at, order.session_token) == (NOW, "sess_1")
    assert events() == ["cart_checkout.checkout.initiated"]
    assert payload("cart_checkout.checkout.initiated") == {
        "id": str(order.id),
        "order_number": "OS-20261014-0001",
        "cart_id": str(order.cart_id),
        "total_amount": 2500,
        "currency": "USD",
    }


def test_the_numbers_follow_each_other_and_start_again_each_business_day(frozen):
    make_cart("sess_1")
    add("sess_1")
    assert initiate().order_number == "OS-20261014-0001"
    assert initiate().order_number == "OS-20261014-0002"
    # 23:30 UTC on the 14th is already the 15th in Madrid: the business's day, not the server's.
    frozen.at(dt.datetime(2026, 10, 14, 23, 30, tzinfo=dt.UTC))
    assert initiate().order_number == "OS-20261015-0001"


def test_the_cart_stays_active_and_its_order_total_no_longer_changes():
    make_cart("sess_1")
    add("sess_1", quantity="1", unit_price=1000)
    order = initiate()
    add("sess_1", quantity="1", unit_price=500, product_ref="p-2")
    assert Cart.objects.get(session_token="sess_1").status == "active"
    assert Order.objects.get(pk=order.id).total_amount == 1000


def test_the_order_takes_the_cart_email_when_none_is_given():
    make_cart("sess_1", customer_email="bea@example.com")
    add("sess_1")
    order = run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    assert order.customer_email == "bea@example.com"


def test_an_order_without_any_email_is_refused_under_its_field():
    make_cart("sess_1")
    add("sess_1")
    OutboxEvent.objects.all().delete()
    with pytest.raises(InvalidPayload) as caught:
        run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    refused(caught, "invalid_field")
    assert caught.value.fields == {"customer_email": "Say the customer's email: the cart has none."}
    assert Order.objects.count() == 0


def test_an_empty_cart_makes_no_order_and_spends_no_number():
    make_cart("sess_1")
    with pytest.raises(Conflict) as caught:
        initiate()
    refused(caught, "cart_checkout.cart_empty")
    assert caught.value.message == "This cart has no lines: add a product before starting the order."
    assert Order.objects.count() == 0
    assert not OrderCounter.objects.filter(last__gt=0).exists()


@pytest.mark.parametrize(("fields", "error"), [({"status": "abandoned"}, Conflict), ({"expires_at": EARLIER}, Conflict)])
def test_a_cart_that_is_not_active_makes_no_order(fields, error):
    cart = make_cart("sess_1", **fields)
    make_item(cart)
    with pytest.raises(error) as caught:
        initiate()
    refused(caught, "cart_checkout.cart_not_active")
    assert Order.objects.count() == 0


def test_a_refused_order_leaves_no_gap_in_the_numbers():
    make_cart("sess_1")
    add("sess_1")
    make_cart("empty")
    assert initiate().order_number == "OS-20261014-0001"
    with pytest.raises(Conflict):
        initiate("empty")
    assert initiate().order_number == "OS-20261014-0002"


def test_initiating_needs_the_checkout_permission():
    make_cart("sess_1")
    add("sess_1")
    with pytest.raises(PermissionDenied):
        run(
            "cart_checkout.checkout.initiate",
            {"session_token": "sess_1", "customer_email": "a@example.com"},
            permissions={"cart_checkout.view_cart", "cart_checkout.manage_cart"},
        )


# ── Orders: steps (CART_CHECKOUT-F09 to F11) ──────────────────────────────────────────────────


def test_marking_an_order_paid_stamps_the_time(frozen):
    order = make_order(order_number="OS-20261014-0003")
    frozen.at(LATER)
    result = run("cart_checkout.order.mark_paid", {"order_number": "os-20261014-0003"}, actor="Bea")
    assert (result.status, result.paid_at) == ("paid", LATER)
    assert Order.objects.get(pk=order.pk).updated_by == "Bea"
    assert events() == ["cart_checkout.order.paid"]
    assert payload("cart_checkout.order.paid") == {
        "id": str(order.id),
        "order_number": "OS-20261014-0003",
        "status": "paid",
        "total_amount": 2500,
        "currency": "EUR",
    }


@pytest.mark.parametrize("status", ["paid", "failed", "completed"])
def test_only_an_initiated_order_is_marked_paid(status):
    order = make_order(status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.mark_paid", {"order_id": str(order.id)})
    refused(caught, "cart_checkout.invalid_transition")
    label = {"paid": "Paid", "failed": "Failed", "completed": "Completed"}[status]
    assert caught.value.message == f"Only an initiated order can be marked as paid; this one is {label}."


@pytest.mark.parametrize("status", ["initiated", "paid"])
def test_failing_an_order_keeps_its_reason(status):
    order = make_order(status=status)
    result = run("cart_checkout.order.fail", {"order_id": str(order.id), "reason": "Card declined"})
    assert (result.status, result.failure_reason, result.failed_at) == ("failed", "Card declined", NOW)
    assert Cart.objects.get(pk=order.cart_id).status == "active"
    assert events() == ["cart_checkout.order.failed"]


@pytest.mark.parametrize("status", ["failed", "completed"])
def test_a_completed_or_failed_order_cannot_fail(status):
    order = make_order(status=status, failure_reason="first")
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.fail", {"order_id": str(order.id), "reason": "again"})
    refused(caught, "cart_checkout.invalid_transition")
    assert Order.objects.get(pk=order.pk).failure_reason == "first"


def test_completing_a_paid_order_converts_its_cart():
    order = make_order(status="paid")
    result = run("cart_checkout.order.complete", {"order_id": str(order.id)})
    assert (result.status, result.completed_at) == ("completed", NOW)
    assert Cart.objects.get(pk=order.cart_id).status == "converted"
    assert events() == ["cart_checkout.order.completed"]


def test_completing_an_order_whose_cart_was_deleted_leaves_the_cart_alone():
    order = make_order(make_cart("gone", deleted_at=EARLIER), status="paid")
    assert run("cart_checkout.order.complete", {"order_id": str(order.id)}).status == "completed"
    assert Cart.objects.get(pk=order.cart_id).status == "active"


@pytest.mark.parametrize("status", ["initiated", "failed", "completed"])
def test_only_a_paid_order_is_completed(status):
    order = make_order(status=status)
    with pytest.raises(Conflict) as caught:
        run("cart_checkout.order.complete", {"order_id": str(order.id)})
    refused(caught, "cart_checkout.invalid_transition")
    assert Cart.objects.get(pk=order.cart_id).status == "active"


def test_an_order_that_does_not_exist_is_refused():
    with pytest.raises(NotFound) as caught:
        run("cart_checkout.order.mark_paid", {"order_number": "OS-20991231-0001"})
    refused(caught, "cart_checkout.order_not_found")


def test_an_employee_cannot_mark_an_order_paid():
    order = make_order()
    with pytest.raises(PermissionDenied):
        run("cart_checkout.order.mark_paid", {"order_id": str(order.id)}, role="hub_employee")
    assert Order.objects.get(pk=order.pk).status == "initiated"


def test_the_refusals_speak_spanish():
    make_cart("sess_1", status="abandoned")
    with translation.override("es"), pytest.raises(Conflict) as caught:
        add("sess_1")
    assert caught.value.message == "Este carrito ya no admite cambios: está Abandonado."
