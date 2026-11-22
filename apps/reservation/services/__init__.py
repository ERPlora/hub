"""Write operations of the reservation app: taking, changing and moving a reservation through its states,
the slots, the blocked dates, the waitlist, the rules, and the reactions to Customers.

Each one is one transaction with its events in the outbox; a refusal writes nothing and announces nothing.

- **The gate** (engine.py) is asked under a lock: every write that books (take, change, convert) first
  locks the book's settings row, so the reservations of a business go one after the other and two of them
  on the last place of a slot, or on the same table and time, leave one.
- **Tables, in the same transaction**: a reservation confirmed, cancelled, not shown
  or deleted calls ``table.hold.sync_reservation``; a confirmed one changed calls it again with its new
  data, or ``table.hold.move_reservation`` when it loses its table; seating calls ``table.session.open``
  with the session of whoever seats and releases with ``table.hold.release`` a hold that was not yet in its
  window. Tables' platform operations are called with only ``table.system`` added to the caller's context.
  The events of the contract (``status_changed``, ``updated``) are recorded as well, for the relay.
- **Customers**: with no card chosen and a phone, the live card with that number is used, or one is
  created, with the caller's session. A typed phone is kept as Customers keeps it (E.164 in the business's
  country, ``apps.customer.phones``), whether the card was chosen or found: the inbox finds the guest's
  conversation by exactly that number (RESERVATION-F19). One that is not a number of its country is refused
  first, with Customers' reason on the phone field.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    reservations as reservations,
    lifecycle as lifecycle,
    slots as slots,
    blocked_dates as blocked_dates,
    waitlist as waitlist,
    settings as settings,
    reactions as reactions,
    writes as writes,
    other_apps as other_apps,
    gate as gate,
    guests as guests,
    seating as seating,
)
