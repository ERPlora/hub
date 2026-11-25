"""Which card an open order is for, as Customers keeps it (CUSTOMER-F19): what the till puts back on a check picked up
again and what Sales charges a check to when the charge names nobody; and the orders of a card, newest first
(``orders_link.pg``)."""

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.customer.models import Customer, OrderLink
from apps.customer.queries.orders import linked_customer_id
from apps.customer.schemas.orders import OrderIn, OrderListIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def test_an_order_is_for_the_live_card_linked_to_it_and_for_nobody_otherwise():
    order = uuid.uuid7()
    assert linked_customer_id(order) is None
    ana = Customer.objects.create(name="Ana García")
    OrderLink.objects.create(order_id=order, customer=ana)
    assert linked_customer_id(order) == ana.id
    assert linked_customer_id(uuid.uuid7()) is None
    Customer.objects.filter(pk=ana.pk).update(deleted_at=timezone.now())
    assert linked_customer_id(order) is None


def test_the_customer_of_an_order():
    order = uuid.uuid7()
    ana = card("Ana")
    assert run("customer.order.customer", OrderIn(order_id=order)).customer_id is None
    OrderLink.objects.create(order_id=order, customer=ana)
    assert run("customer.order.customer", OrderIn(order_id=order)).model_dump() == {
        "order_id": order,
        "customer_id": ana.id,
    }
    Customer.objects.filter(pk=ana.pk).update(deleted_at=timezone.now())
    # A card that is no longer available is no customer of the order: the till asks again.
    assert run("customer.order.customer", OrderIn(order_id=order)).customer_id is None


def test_the_orders_of_a_customer_newest_first():
    ana = card("Ana")
    old = OrderLink.objects.create(
        order_id=uuid.uuid7(), customer=ana, linked_at=NOW - timedelta(hours=1)
    )
    new = OrderLink.objects.create(order_id=uuid.uuid7(), customer=ana, linked_at=NOW)
    OrderLink.objects.create(order_id=uuid.uuid7(), customer=card("Bea"))
    page = run("customer.order.list", OrderListIn(customer_id=ana.id))
    assert [row.order_id for row in page.rows] == [new.order_id, old.order_id]
