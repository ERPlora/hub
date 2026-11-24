"""Write operations of the pricing app: one operation = one transaction, with its events in the outbox.

A refusal writes nothing and records no event; it carries the field it is about, so the form puts it
next to it. Codes are unique whatever their case (the database's index decides, also between two
people saving at once); at most one list is general: making one general takes the mark from the other
in a savepoint, and if another choice wins the race (the index says so), it is tried again, so the last
one stays (WORKBOOK «Para quien lo mantiene»). A write that names another app's row (a rule's category or
product, a price's product, a list's or a rule's customer group) holds it until it ends (Inventory's
``held``): its deletion waits for the write, and one under way when it is read is not found, as one deleted
before.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    price_lists as price_lists,
    prices as prices,
    rules as rules,
    catalog as catalog,
    writes as writes,
)
