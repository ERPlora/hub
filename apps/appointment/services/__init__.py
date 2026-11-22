"""Write operations of the appointment app: one operation = one transaction, with its events in the outbox.

- **Every check runs before the first write**, so a refusal leaves no trace (no row, no history line, no
  event).
- **Overlaps are decided under a lock**: booking, moving and editing lock the professional's staff record
  first (``resolve_member(lock=True)``; two of them in id order), so two bookings of the same
  professional at once wait for each other and the second one sees the first.
- **The front desk overlaps knowingly**: with overlaps allowed, a booking that touches another
  appointment of the professional is refused with 409 ``appointment.overlap_needs_confirmation`` (naming
  what it touches) until it is sent again with ``confirm_overlap``; with them off, it is
  ``appointment.slot_taken``. The customer (``online``, ``whatsapp``) and the series never overlap, and
  keep the notice and the past.
- **Charged is final**: a charged appointment is completed and is not moved, cancelled, marked a no-show
  nor deleted (void the sale first); a cancelled or no-show one is not charged.
- **Several rows, one order**: a write that locks several appointments or series takes them in id order
  (``lock_appointments``, ``lock_series``), the series before their appointments, as the Hub admin's «Delete»
  does; then it reads them in its own order. Two writes never wait for each other in a circle.
- The platform's reactions (``SYSTEM``) are run by the outbox relay as the system; they are idempotent.
"""

# Not alphabetical: this is the order the operations register in.
from . import (
    writes as writes,
    booking as booking,
    moving as moving,
    states as states,
    deleting as deleting,
    charging as charging,
    blocked_times as blocked_times,
    series as series,
    series_update as series_update,
    series_states as series_states,
    settings as settings,
    reactions as reactions,
)
