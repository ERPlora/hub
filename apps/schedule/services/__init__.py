"""Write operations of the schedule app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). The rules of the
intervals are ``schemas.intervals.check_intervals`` (engine.py underneath), applied again here to what a
correction leaves. Writes on the temporary changes lock the settings row first, so two that would
cover the same day never slip past each other's check; a special day's date is unique in the database.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (the week, the special days, the temporary changes and the settings), and the helpers follow.
from . import (
    week as week,
    special_days as special_days,
    overrides as overrides,
    settings as settings,
    writes as writes,
)
