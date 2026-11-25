"""Read operations of the reservation app (``READ ONLY``): the reservations, one reservation, a day's
figures and slots, the free tables, the slots, the blocked dates, the waitlist and the rules. A read by id
(a reservation, a waitlist entry, a slot, a blocked date) also answers its ``label``: the words the book's
screens name it by, which the assistant's card says instead of the id (schemas/fields.py, ``names``).

Shared with the writes (services/), inside the command's own transaction: the business's clock, the rules, the
lookups of a reservation, a waitlist entry, a slot or a blocked date as a person says it, and everything the gate
(engine.py) reads — the slots of a day with what they hold, its blocks, its opening hours (Schedules) and a table's
facts (Tables). The business's zone is the Hub's (``base.business.business_zone``).
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    reservations as reservations,
    availability as availability,
    slots as slots,
    blocked_dates as blocked_dates,
    waitlist as waitlist,
    settings as settings,
    clock as clock,
    rows as rows,
    lookups as lookups,
    gate as gate,
)
