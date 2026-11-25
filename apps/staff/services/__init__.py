"""Write operations of the staff app: one operation = one transaction, with its events in the outbox.

A refused command leaves no trace (the transaction rolls back: no row, no event). Every write on a
staff member locks the member's row first, so two requests on the same person never interleave
(two time-off requests at once cannot both slip past the overlap check). Events carry ids only.
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    members as members,
    roles as roles,
    schedules as schedules,
    time_off as time_off,
    settings as settings,
    locks as locks,
)
