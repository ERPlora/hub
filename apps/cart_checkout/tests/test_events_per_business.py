"""Every event of the cart_checkout app that an operation of business B records stays in B's own database, with B's
scope, and none reaches business A's.

Automations starts the automations of the business named by the outbox row, while the live notice goes to the channel
of the operation's scope: only the row shows an event recorded with another business."""

import datetime as dt
from collections.abc import Callable

import pytest
from django.utils import timezone
from live.models import OutboxEvent

from apps.cart_checkout import events
from base.tenancy.context import use_hub

from .conftest import HUB_DB, B, make_cart, make_item, make_order
from .test_services import run

pytestmark = HUB_DB

TOKEN = "sess_b"


def a_cart() -> dict:
    make_cart(TOKEN, customer_email="bea@example.com")
    return {"session_token": TOKEN}


def a_cart_with_a_line() -> dict:
    make_item(make_cart(TOKEN, customer_email="bea@example.com"))
    return {"session_token": TOKEN}


def an_overdue_cart() -> dict:
    make_cart(TOKEN, expires_at=timezone.now() - dt.timedelta(hours=1))
    return {}


def a_line() -> dict:
    return {"item_id": str(make_item(make_cart(TOKEN)).id)}


def a_new_line() -> dict:
    return a_cart() | {"product_ref": "p-1", "product_name": "Champú", "quantity": "1", "unit_price": 1250}


def an_order(status: str) -> Callable[[], dict]:
    def build() -> dict:
        return {"order_id": str(make_order(make_cart(TOKEN), status=status).id)}

    return build


def an_initiated_order_to_fail() -> dict:
    return an_order("initiated")() | {"reason": "Card declined"}


def a_customer() -> dict:
    a_cart()
    return {"email": "bea@example.com"}


#: Each event, the operation that records it and what B holds before the operation runs.
CASES = [
    (events.CART_CREATED, "cart_checkout.cart.create", lambda: {"session_token": TOKEN}),
    (events.CART_ABANDONED, "cart_checkout.cart.mark_abandoned", a_cart),
    (events.CART_DELETED, "cart_checkout.cart.delete", a_cart),
    (events.CART_CLEARED, "cart_checkout.cart.clear", a_cart_with_a_line),
    (events.CART_EXPIRED, "cart_checkout.cart.cleanup_expired", an_overdue_cart),
    (events.ITEM_ADDED, "cart_checkout.item.add", a_new_line),
    (events.ITEM_UPDATED, "cart_checkout.item.update", lambda: a_line() | {"quantity": "2"}),
    (events.ITEM_REMOVED, "cart_checkout.item.remove", a_line),
    (events.CHECKOUT_INITIATED, "cart_checkout.checkout.initiate", a_cart_with_a_line),
    (events.ORDER_PAID, "cart_checkout.order.mark_paid", an_order("initiated")),
    (events.ORDER_FAILED, "cart_checkout.order.fail", an_initiated_order_to_fail),
    (events.ORDER_COMPLETED, "cart_checkout.order.complete", an_order("paid")),
    (events.CUSTOMER_ERASED, "cart_checkout.customer.erase", a_customer),
]


def recorded() -> list[tuple[str, str, str]]:
    """The events in the database of the business at work, with the scope each was recorded with."""
    return list(OutboxEvent.objects.order_by("id").values_list("scope_kind", "scope_key", "name"))


def test_every_event_of_the_app_has_its_case():
    assert sorted(event for event, _, _ in CASES) == sorted(events.ALL)


@pytest.mark.parametrize(("event", "operation", "before"), CASES, ids=[event for event, _, _ in CASES])
def test_an_event_of_b_is_recorded_in_b_with_b_s_scope_and_never_in_a(hub_b, event, operation, before):
    with use_hub(hub_b):
        data = before()
        run(operation, data, scope=B)
        assert recorded() == [(B.kind, B.key, event)]
    assert recorded() == [], "business A's database got an event of B"
