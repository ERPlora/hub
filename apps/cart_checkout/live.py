"""Live queries of the cart_checkout app and the events that re-run them after the COMMIT.

A cart's lines change its totals; completing an order converts its cart; clearing or deleting a cart
takes its lines away; erasing a customer's personal data empties fields of their carts and orders.
"""

from live.live_registry import live

from apps.cart_checkout.events import (
    CART_CLEARED,
    CART_DELETED,
    CART_EVENTS,
    CUSTOMER_ERASED,
    ITEM_EVENTS,
    ORDER_COMPLETED,
    ORDER_EVENTS,
)

live("cart_checkout.cart.list", on=[*CART_EVENTS, *ITEM_EVENTS, ORDER_COMPLETED, CUSTOMER_ERASED])
live("cart_checkout.cart.get", on=[*CART_EVENTS, *ITEM_EVENTS, ORDER_COMPLETED, CUSTOMER_ERASED])
live("cart_checkout.item.list", on=[*ITEM_EVENTS, CART_CLEARED, CART_DELETED])
live("cart_checkout.item.get", on=[*ITEM_EVENTS, CART_CLEARED, CART_DELETED])
live("cart_checkout.order.list", on=[*ORDER_EVENTS, CUSTOMER_ERASED])
live("cart_checkout.order.get", on=[*ORDER_EVENTS, CUSTOMER_ERASED])
