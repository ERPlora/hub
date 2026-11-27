"""Write operations of the cart_checkout app: carts (create, abandon, delete, clear, expire), their lines
(add, change, remove) and the orders made from them (initiate with their number of the day, mark paid,
fail, complete).

The cases come from the old module's WORKFLOW, its tests and its handler (Rust), with its silent no-ops
turned into refusals: an action on a cart that is not active, a step from the wrong state, or an order
from an empty cart says why, changes nothing, spends no number and records no event
(CART_CHECKOUT-F02 to F11 «parcial»).

Each module of services/ has its cases in test_services_<module>.py; here, what every operation declares,
the whole flow from a new cart to a completed order and the notifications after the COMMIT.
"""

import json

import pytest
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.cart_checkout.models import Cart, Order
from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, add, events, make_order, run

pytestmark = HUB_DB

WAIT = 1.0
QUIET = 0.3


@pytest.fixture(autouse=True)
def frozen(clock):
    return clock


@pytest.mark.parametrize(
    ("name", "permission"),
    [
        ("cart_checkout.cart.create", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.mark_abandoned", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.delete", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.clear", "cart_checkout.manage_cart"),
        ("cart_checkout.cart.cleanup_expired", "cart_checkout.manage_cart"),
        ("cart_checkout.item.add", "cart_checkout.manage_cart"),
        ("cart_checkout.item.update", "cart_checkout.manage_cart"),
        ("cart_checkout.item.remove", "cart_checkout.manage_cart"),
        ("cart_checkout.checkout.initiate", "cart_checkout.checkout"),
        ("cart_checkout.order.mark_paid", "cart_checkout.checkout"),
        ("cart_checkout.order.fail", "cart_checkout.checkout"),
        ("cart_checkout.order.complete", "cart_checkout.checkout"),
        ("cart_checkout.customer.erase", "cart_checkout.manage_cart"),
    ],
)
def test_declarations(name, permission):
    op = get(name)
    assert (op.kind, op.permission, op.expose_api) == ("command", permission, True)


# ── The whole flow, as the old module's screens and assistant run it ─────────────────────────


def test_from_a_new_cart_to_a_completed_order():
    cart = run("cart_checkout.cart.create", {"session_token": "sess_1", "customer_email": "ana@example.com"})
    add("sess_1", quantity="2", unit_price=1250)
    order = run("cart_checkout.checkout.initiate", {"session_token": "sess_1"})
    run("cart_checkout.order.mark_paid", {"order_number": order.order_number})
    run("cart_checkout.order.complete", {"order_number": order.order_number})
    assert Cart.objects.get(pk=cart.id).status == "converted"
    assert Order.objects.get(pk=order.id).status == "completed"
    assert events() == [
        "cart_checkout.cart.created",
        "cart_checkout.item.added",
        "cart_checkout.checkout.initiated",
        "cart_checkout.order.paid",
        "cart_checkout.order.completed",
    ]


# ── Notifications: after the COMMIT, on the channel of the command's scope only ───────────────


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


def scopes_of_the_events() -> list[tuple[str, str]]:
    """The scope each event of the business at work was recorded with."""
    return list(OutboxEvent.objects.values_list("scope_kind", "scope_key"))


@HUB_DB_COMMITTED
def test_a_cart_created_in_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        run("cart_checkout.cart.create", {"session_token": "sess_b"}, scope=B)
        assert scopes_of_the_events() == [(B.kind, B.key)]
    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": ["cart_checkout.cart.created"]})]
    assert received(on_a, timeout=QUIET) == []
    assert scopes_of_the_events() == []


@HUB_DB_COMMITTED
def test_a_refused_step_notifies_nobody(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        order = make_order(status="completed")
        with pytest.raises(Conflict):
            run("cart_checkout.order.mark_paid", {"order_id": str(order.id)}, scope=B)
        assert scopes_of_the_events() == []
    assert received(on_b, timeout=QUIET) == []
    assert received(on_a, timeout=QUIET) == []
