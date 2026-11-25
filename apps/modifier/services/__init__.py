"""Write operations of the modifier app: one operation = one transaction, with its events in the outbox.

Every check runs before anything is written, so a refusal leaves no trace. A name another row took in
the meantime (two people saving at once) is caught as the database's unique constraint, in a
savepoint, and refused with the same 409 as the check. Changing a row only changes what was sent and
says so only when something changed. A group's row is locked before its options' defaults are
counted, so two saves of the same group wait for each other. What a write names in another app (the
product or category a group is applied to, an option's tax category) is held until it commits (Inventory's
``held``): a deletion at the same time waits for it, or ends first and the write finds it gone.
"""

# Importing a module registers its operations: the modules with operations come first, and the helpers follow.
from . import (
    groups as groups,
    options as options,
    links as links,
    recovery as recovery,
    defaults as defaults,
    writes as writes,
)
