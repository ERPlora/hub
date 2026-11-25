"""Write operations of the payment app: one operation = one transaction, with its events in the outbox.

Every check runs before the first write, so a refusal leaves no trace: no row, no reference number
spent, no event (the old module answered «ok» to a step from the wrong state, spent a number on a
payment it did not save and emitted the event anyway). A step locks the payment's row first, so two
people pressing at once go one after the other and the second hears why. The reference of the day
comes from the counter's row raised with ``UPDATE … RETURNING`` in the payment's transaction (never a
sequence). A method name two saves take at once ends in the database's unique constraint, translated
to the same 409 as the check. A payment sent with the key of its attempt is recorded once: the same
attempt sent again (a retry, a double tap, both at once) answers the payment already recorded, without
a second number or notice.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (the methods, then the payments), and the helper follows.
from . import (
    methods as methods,
    payments as payments,
    actor as actor,
)
