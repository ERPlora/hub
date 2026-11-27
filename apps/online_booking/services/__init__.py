"""Write operations of the online booking app: one operation = one transaction, with its events in the outbox.

- **The diary does it**: confirming, completing, a no-show, cancelling and deleting a booking are the
  operations of Citas, run by name with the caller's own context (this app's right and the diary's, both).
- **The public booking** checks the page (on, the services online, the professional's choice, the form),
  the limits (per visitor and hour, per business and hour, upcoming per mobile), finds the customer's card by
  her mobile or creates it (``customer.customer.create``), and books with ``appointment.appointment.create``
  (``source = "online"``: the diary's notice, window, no overlap and auto-confirm). With «anyone», each
  professional who does the services is tried in name order, each attempt in its own savepoint. Then the
  link: a random token handed out once, kept as its hash.
- **Every check runs before the first write** or rolls back with it: a refusal leaves no appointment, no
  card, no link and no event.
- The platform's reaction (``SYSTEM``) is run by the outbox relay as the system; it is idempotent.
"""

# Importing a module registers its operations: they come in the order the registry lists them, not alphabetical.
from . import (
    logo as logo,
    bookings as bookings,
    settings as settings,
    public_booking as public_booking,
    links as links,
    reactions as reactions,
)
