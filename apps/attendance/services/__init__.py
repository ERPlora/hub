"""Write operations of the attendance app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). Every write on a
person's working days locks that person's staff record first (``FOR NO KEY UPDATE``, which never holds
up Staff's own writes on it), so two taps at once, or a correction against a clock-in, wait for each
other and decide on what the first one left. The partial unique indexes (one open day per person, one
running break per day) still hold whatever door writes; hitting one is turned into the same 409.
Times are the server's (``timezone.now()``); the distance to the workplace is measured here.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (clocking in and out, the breaks, the corrections, the settings, what the system runs), and the helpers
# follow.
from . import (
    clocking as clocking,
    breaks as breaks,
    corrections as corrections,
    settings as settings,
    system as system,
    days as days,
    location as location,
)
