"""The cart_checkout app's event vocabulary: ``cart_checkout.<entity>.<fact in the past tense>``.

The old module's twelve events keep their facts; only ``carts.expired`` takes its entity in the singular
(``cart.expired``). No app of the Hub listens to them, and this app reacts to no event of another one.
"""

import re

from live.operations import NAME_RE

from apps.cart_checkout import events

#: A fact in the past: «-ed», or «paid» (irregular, the old module's own word).
PAST_FACT = re.compile(r"^cart_checkout\.(cart|item|checkout|order|customer)\.([a-z_]+ed|paid)$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_twelve_events_of_the_old_module_and_the_erasure():
    assert declared() == {
        "CART_CREATED": "cart_checkout.cart.created",
        "CART_ABANDONED": "cart_checkout.cart.abandoned",
        "CART_DELETED": "cart_checkout.cart.deleted",
        "CART_CLEARED": "cart_checkout.cart.cleared",
        "CART_EXPIRED": "cart_checkout.cart.expired",
        "ITEM_ADDED": "cart_checkout.item.added",
        "ITEM_UPDATED": "cart_checkout.item.updated",
        "ITEM_REMOVED": "cart_checkout.item.removed",
        "CHECKOUT_INITIATED": "cart_checkout.checkout.initiated",
        "ORDER_PAID": "cart_checkout.order.paid",
        "ORDER_FAILED": "cart_checkout.order.failed",
        "ORDER_COMPLETED": "cart_checkout.order.completed",
        "CUSTOMER_ERASED": "cart_checkout.customer.erased",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_the_events_are_grouped_by_what_they_change():
    assert events.CART_EVENTS == [
        events.CART_CREATED,
        events.CART_ABANDONED,
        events.CART_DELETED,
        events.CART_CLEARED,
        events.CART_EXPIRED,
    ]
    assert events.ITEM_EVENTS == [events.ITEM_ADDED, events.ITEM_UPDATED, events.ITEM_REMOVED]
    assert events.ORDER_EVENTS == [
        events.CHECKOUT_INITIATED,
        events.ORDER_PAID,
        events.ORDER_FAILED,
        events.ORDER_COMPLETED,
    ]
    assert events.CUSTOMER_EVENTS == [events.CUSTOMER_ERASED]
    assert events.ALL == events.CART_EVENTS + events.ITEM_EVENTS + events.ORDER_EVENTS + events.CUSTOMER_EVENTS


def test_it_listens_to_nobody():
    # No foreign key to Customers or Inventory (WORKBOOK «Decisión»): no reaction to their events.
    assert not hasattr(events, "react")
