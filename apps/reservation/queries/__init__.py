"""Read operations of the reservation app (``READ ONLY``): the reservations, one reservation, a day's
figures and slots, the free tables, the slots, the blocked dates, the waitlist and the rules. A read by id
(a reservation, a waitlist entry, a slot, a blocked date) also answers its ``label``: the words the book's
screens name it by, which the assistant's card says instead of the id (schemas/fields.py, ``names``).

Shared with ``services``, inside the command's own transaction: the business's clock and the rules (``business``), the
lookup of a record as a person says it (each in its own module) and everything the gate reads (``gate``).
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    reservations as reservations,
    availability as availability,
    slots as slots,
    blocked_dates as blocked_dates,
    waitlist as waitlist,
    settings as settings,
    business as business,
    gate as gate,
    naming as naming,
    reads as reads,
)
