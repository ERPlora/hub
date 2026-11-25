"""Read operations of the online booking app (``READ ONLY``), and the helpers its services reuse inside their own
transaction: the page's settings, the inbox over the diary's online appointments, how a booking is named,
the public context and the visitor's fingerprint.

- **A booking is an appointment** of Citas with ``source = "online"``: the inbox reads the diary's table (Citas
  is a requirement) and who sees what is the diary's rule (``appointment.queries.ownership.APPOINTMENTS``: the
  employee sees her own agenda).
- **The public reads** (``online_booking.public``) answer only while the page is on, and ask the other apps
  with ``delegated(ctx)``: the same context with exactly what they need of Citas, Clientes, Servicios,
  Horarios and Personal (as ``appointment.queries.agenda.reader`` does), never a role's.
- Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break.
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    bookings as bookings,
    settings as settings,
    page as page,
    offer as offer,
    links as links,
    visitors as visitors,
)
