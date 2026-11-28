"""Read operations of the cart_checkout app (``READ ONLY``): the carts, one cart with its lines, the lines
of a cart, one line, the orders and one order.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break, so pages never overlap. A deleted
cart is never read. An active cart past its expiry reads as expired everywhere (its ``status`` is
computed when read: nobody has to run the expiry first). The ``find_*`` helpers resolve how a person
names a record (assistant, voice): a cart by its id, its session code, or its customer (exact email,
else part of the name; among several carts of one customer, the only active one; carts of different
customers, or several active ones, 409 ``cart_checkout.cart_ambiguous`` naming their codes); an order by
its id or its number; a line by its id. services/ uses them too,
inside its own transaction.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (the carts, their lines, the orders), and the helpers follow.
from . import (
    carts as carts,
    items as items,
    orders as orders,
    reads as reads,
    rows as rows,
)
