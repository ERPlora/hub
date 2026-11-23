"""Which card an open order is for, as Customers keeps it (CUSTOMER-F19): what the till puts back on a check picked up
again and what Sales charges a check to when the charge names nobody."""

import uuid

from django.utils import timezone

from apps.customer.models import Customer, OrderLink
from apps.customer.queries.orders import linked_customer_id

from .conftest import HUB_DB

pytestmark = HUB_DB


def test_an_order_is_for_the_live_card_linked_to_it_and_for_nobody_otherwise():
    order = uuid.uuid7()
    assert linked_customer_id(order) is None
    ana = Customer.objects.create(name="Ana García")
    OrderLink.objects.create(order_id=order, customer=ana)
    assert linked_customer_id(order) == ana.id
    Customer.objects.filter(pk=ana.pk).update(deleted_at=timezone.now())
    assert linked_customer_id(order) is None
