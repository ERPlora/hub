"""Write operations of the cart_checkout app: one operation = one transaction, with its events in the
outbox.

Every check runs before the first write, so a refusal leaves no trace: no row, no order number spent, no
event (the old module answered «ok» to an action on a cart that was not active or to a step from the
wrong state, spent an order number on an order it did not save and emitted the event anyway). An action
locks the cart's row first (and then its line or its order), so two people at once go one after the
other and the second hears why. The order number of the day comes from the counter's row raised with
``UPDATE … RETURNING`` in the order's transaction (never a sequence). A session code two saves take at
once ends in the database's unique constraint, translated to the same 409 as the check.

Nothing here is fiscal and nothing charges: «paid» is a mark a person sets after charging some other
way; no sale, invoice, VeriFactu record, cash or stock movement is created.
"""

# Importing a module registers its operations, in this order.
from . import (
    carts as carts,
    items as items,
    orders as orders,
    personal_data as personal_data,
)
