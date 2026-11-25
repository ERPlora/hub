"""The order a card is linked to (CUSTOMER-F19)."""

import uuid

import pytest
from live.errors import NotFound

from apps.customer import events
from apps.customer.models import OrderLink
from apps.customer.schemas.orders import OrderLinkIn

from .conftest import HUB_DB, NOW, card, outbox, run

pytestmark = HUB_DB


# customer.order.link (CUSTOMER-F19; orders_link.pg)


def test_an_order_has_at_most_one_customer_and_a_relink_replaces_it():
    order = uuid.uuid7()
    ana, bea = card("Ana"), card("Bea")
    assert (
        run(
            "customer.order.link",
            OrderLinkIn(order_id=order, customer_id=ana.id),
            "hub_employee",
        ).customer_id
        == ana.id
    )
    run(
        "customer.order.link", OrderLinkIn(order_id=order, customer_id=ana.id)
    )  # the same pair: nothing rewritten
    assert (
        run(
            "customer.order.link", OrderLinkIn(order_id=order, customer="Bea")
        ).customer_id
        == bea.id
    )
    assert list(OrderLink.objects.values_list("order_id", "customer_id")) == [
        (order, bea.id)
    ]
    assert outbox() == [
        (events.ORDER_LINKED, {"order_id": str(order), "customer_id": str(ana.id)}),
        (events.ORDER_LINKED, {"order_id": str(order), "customer_id": str(bea.id)}),
    ]


def test_without_a_customer_the_link_goes():
    order = uuid.uuid7()
    ana = card("Ana")
    OrderLink.objects.create(order_id=order, customer=ana)
    assert run("customer.order.link", OrderLinkIn(order_id=order)).customer_id is None
    assert not OrderLink.objects.exists()
    run(
        "customer.order.link", OrderLinkIn(order_id=order)
    )  # nothing to remove: no notice
    assert outbox() == [
        (events.ORDER_UNLINKED, {"order_id": str(order), "customer_id": str(ana.id)})
    ]


def test_a_card_that_is_gone_is_not_linked():
    with pytest.raises(NotFound):
        run(
            "customer.order.link",
            OrderLinkIn(
                order_id=uuid.uuid7(), customer_id=card("Gone", deleted_at=NOW).id
            ),
        )
