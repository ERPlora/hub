"""Write operations of the kitchen app: one operation = one transaction, with its events in the outbox and
its line in the History.

Every write that touches a ticket starts by **settling** (``settle``): it locks the settings row (so every
write of the kitchen of a business goes one after the other: two cooks at once never step on each
other), saves the rounds Sales fired that the kitchen has not saved yet (the ones the relay's reaction
has not brought yet, queries.rounds) and saves what Sales did to the tickets (``queries.state.effective``),
with its History at the moment it happened, its events and its void slips. Then the operation finds its ticket,
already saved.

Paper goes through Printing's operation by its name (``printing.job.create``), in a savepoint of the same
transaction: Printing off or absent is no paper and no error; any other refusal comes back in
``print_error`` and never undoes the kitchen's action (KITCHEN-F08).
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    rounds as rounds,
    by_hand as by_hand,
    journey as journey,
    dishes as dishes,
    stations as stations,
    routing as routing,
    settings as settings,
    writes as writes,
    settling as settling,
    paper as paper,
    catalog as catalog,
)
