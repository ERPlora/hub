"""Live queries of the cart_checkout app: which events re-run which query after the COMMIT.

The old screens re-read their lists on the events they listened to (Carts on the cart and line events and
on a completed order, Orders on the order events); here the server re-runs the subscribed query and sends
the result. A cart's lines change its totals; completing an order converts its cart; deleting or clearing
a cart takes its lines.
"""

from pathlib import Path

from live.live_registry import live_registry

from apps.cart_checkout import events

EVENTS_SOURCE = Path(events.__file__).read_text()
CART = [
    "cart_checkout.cart.created",
    "cart_checkout.cart.abandoned",
    "cart_checkout.cart.deleted",
    "cart_checkout.cart.cleared",
    "cart_checkout.cart.expired",
]
ITEM = ["cart_checkout.item.added", "cart_checkout.item.updated", "cart_checkout.item.removed"]
#: Erasing a customer's personal data empties fields of their carts and orders.
ERASED = "cart_checkout.customer.erased"
ORDER = [
    "cart_checkout.checkout.initiated",
    "cart_checkout.order.paid",
    "cart_checkout.order.failed",
    "cart_checkout.order.completed",
]


def subscribable():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("cart_checkout.")
    }


def affected(event):
    return {name for name in live_registry.affected([event]) if name.startswith("cart_checkout.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert subscribable() == {
        "cart_checkout.cart.list": [*CART, *ITEM, "cart_checkout.order.completed", ERASED],
        "cart_checkout.cart.get": [*CART, *ITEM, "cart_checkout.order.completed", ERASED],
        "cart_checkout.item.list": [*ITEM, "cart_checkout.cart.cleared", "cart_checkout.cart.deleted"],
        "cart_checkout.item.get": [*ITEM, "cart_checkout.cart.cleared", "cart_checkout.cart.deleted"],
        "cart_checkout.order.list": [*ORDER, ERASED],
        "cart_checkout.order.get": [*ORDER, ERASED],
    }


def test_every_event_is_a_literal_of_events_py():
    for on in subscribable().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_new_line_re_runs_the_carts_and_the_lines_not_the_orders():
    assert affected(events.ITEM_ADDED) == {
        "cart_checkout.cart.list",
        "cart_checkout.cart.get",
        "cart_checkout.item.list",
        "cart_checkout.item.get",
    }


def test_completing_an_order_re_runs_the_orders_and_the_carts():
    assert affected(events.ORDER_COMPLETED) == {
        "cart_checkout.order.list",
        "cart_checkout.order.get",
        "cart_checkout.cart.list",
        "cart_checkout.cart.get",
    }


def test_a_paid_order_re_runs_the_orders_only():
    assert affected(events.ORDER_PAID) == {"cart_checkout.order.list", "cart_checkout.order.get"}


def test_erasing_a_customer_re_runs_the_carts_and_the_orders_not_the_lines():
    assert affected(events.CUSTOMER_ERASED) == {
        "cart_checkout.cart.list",
        "cart_checkout.cart.get",
        "cart_checkout.order.list",
        "cart_checkout.order.get",
    }
