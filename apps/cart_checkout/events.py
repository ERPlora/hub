"""Events of the cart_checkout app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

Each one is written in the transaction of its change, and only when the change happened: a refused
action leaves no event (the old module emitted them anyway). Only the flow app listens to them (it hears
every event, FLOW-F21), and this app reacts to no event of another one (no link to Customers or
Inventory), so this module declares no ``REACTIONS`` and only names its own.
"""

CART_CREATED = "cart_checkout.cart.created"
CART_ABANDONED = "cart_checkout.cart.abandoned"
CART_DELETED = "cart_checkout.cart.deleted"
CART_CLEARED = "cart_checkout.cart.cleared"
CART_EXPIRED = "cart_checkout.cart.expired"
ITEM_ADDED = "cart_checkout.item.added"
ITEM_UPDATED = "cart_checkout.item.updated"
ITEM_REMOVED = "cart_checkout.item.removed"
CHECKOUT_INITIATED = "cart_checkout.checkout.initiated"
ORDER_PAID = "cart_checkout.order.paid"
ORDER_FAILED = "cart_checkout.order.failed"
ORDER_COMPLETED = "cart_checkout.order.completed"
CUSTOMER_ERASED = "cart_checkout.customer.erased"

CART_EVENTS = [CART_CREATED, CART_ABANDONED, CART_DELETED, CART_CLEARED, CART_EXPIRED]
ITEM_EVENTS = [ITEM_ADDED, ITEM_UPDATED, ITEM_REMOVED]
ORDER_EVENTS = [CHECKOUT_INITIATED, ORDER_PAID, ORDER_FAILED, ORDER_COMPLETED]
CUSTOMER_EVENTS = [CUSTOMER_ERASED]
ALL = CART_EVENTS + ITEM_EVENTS + ORDER_EVENTS + CUSTOMER_EVENTS
