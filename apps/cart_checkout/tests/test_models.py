"""Models of the cart_checkout app: what the database itself refuses, the defaults and how a row reads."""

import datetime as dt
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.cart_checkout.models import Cart, CartItem, Order, OrderCounter

from .conftest import make_cart, make_item, make_order

pytestmark = pytest.mark.django_db


def test_a_cart_is_born_active_empty_and_in_euros():
    cart = make_cart("sess_1")
    assert cart.status == Cart.Status.ACTIVE
    assert (cart.total_items, cart.total_amount, cart.currency) == (Decimal("0"), 0, "EUR")
    assert (cart.customer_email, cart.customer_name, cart.notes) == ("", "", "")
    assert (cart.expires_at, cart.last_activity_at, cart.deleted_at) == (None, None, None)
    assert cart.abandon_reason == ""
    assert str(cart) == "sess_1"


def test_the_four_cart_statuses_of_the_old_module():
    assert [value for value, _ in Cart.Status.choices] == [
        "active",
        "abandoned",
        "converted",
        "expired",
    ]


def test_a_session_code_is_unique_among_the_carts_not_deleted():
    first = make_cart("sess_1")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_cart("sess_1")
    # A deleted cart frees its code for another one.
    first.deleted_at = dt.datetime(2026, 10, 14, tzinfo=dt.UTC)
    first.save()
    assert make_cart("sess_1").pk != first.pk


def test_the_database_refuses_an_unknown_status_or_negative_totals():
    with pytest.raises(IntegrityError), transaction.atomic():
        make_cart("s1", status="lost")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_cart("s2", total_amount=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_cart("s3", total_items=Decimal("-1"))


def test_a_line_belongs_to_its_cart():
    cart = make_cart()
    line = make_item(cart, quantity=Decimal("0.5"), unit_price=1200, line_total=600)
    assert list(cart.items.all()) == [line]
    assert line.variant_attributes == {}
    assert line.sku == ""
    assert str(line) == "Champú × 0.500"


def test_the_database_refuses_a_line_without_quantity_or_with_a_negative_price():
    cart = make_cart()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(cart, quantity=Decimal("0"))
    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(cart, unit_price=-1, line_total=0)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_item(cart, line_total=-1)


def test_an_order_is_initiated_in_euros_by_default():
    order = make_order()
    assert order.status == Order.Status.INITIATED
    assert order.currency == "EUR"
    assert (order.shipping_address, order.billing_address) == ({}, {})
    assert (order.shipping_method, order.payment_method, order.notes) == ("", "", "")
    assert order.failure_reason == ""
    assert (order.placed_at, order.paid_at, order.failed_at, order.completed_at) == (
        None,
        None,
        None,
        None,
    )
    assert str(order) == "OS-20261014-0001"


def test_an_erased_order_keeps_no_email():
    # CART_CHECKOUT-F14: erasing a customer's personal data leaves the order without an email; the admin
    # must still save it.
    assert Order._meta.get_field("customer_email").blank is True


def test_the_four_order_statuses_of_the_old_module():
    assert [value for value, _ in Order.Status.choices] == [
        "initiated",
        "paid",
        "failed",
        "completed",
    ]


def test_an_order_number_is_unique_and_the_database_refuses_an_unknown_status():
    cart = make_cart()
    make_order(cart)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(cart)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(cart, order_number="OS-20261014-0002", status="refunded")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_order(cart, order_number="OS-20261014-0003", total_amount=-5)


def test_a_cart_with_orders_cannot_be_dropped_from_the_database():
    # Deleting is logical (deleted_at); a hard delete (the admin) never takes its orders with it.
    order = make_order()
    with pytest.raises(ProtectedError):
        order.cart.delete()


def test_dropping_a_cart_without_orders_drops_its_lines():
    cart = make_cart()
    make_item(cart)
    cart.delete()
    assert CartItem.objects.count() == 0


def test_the_counter_keeps_the_last_number_of_a_day():
    counter = OrderCounter.objects.create(day=dt.date(2026, 10, 14))
    assert counter.last == 0
    assert str(counter) == "2026-10-14: 0"
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderCounter.objects.create(day=dt.date(2026, 10, 14))


def test_the_lists_read_newest_first():
    make_cart("old")
    newer = make_cart("new")
    assert Cart.objects.first() == newer
