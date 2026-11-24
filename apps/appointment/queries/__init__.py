"""Read operations of the appointment app (``READ ONLY``), and the helpers services.py reuses inside its
own transaction: the business's clock, the settings, who sees what, how a booking's customer, services
and professional are resolved, and the agenda the rules (engine.py) judge.

- **Who sees what** (``ownership.py``): ``appointment.view_appointment`` sees the whole diary; ``…view_own_appointment``
  only the appointments and series of the staff record linked to the caller's account (none when it has none).
- **Availability = Schedules ∩ Staff ∩ appointments**: ``load_agenda`` reads ``schedule.hours.for_range``
  and ``staff.availability.for_member`` (their operations, with a reading context that adds
  ``schedule.view`` and ``staff.view``: booking needs no right in those apps), the blocks and the
  professional's appointments, and hands them to ``engine``.
- **Who may do a service**: the active, bookable professionals with an active assignment for it; a
  service nobody is assigned to may be done by the whole bookable team (the diary's rule, not Staff's
  nor Services'). Several services: whoever may do every one.
- Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break.
"""

# Not alphabetical: the ones that register operations go first, in the order they register in.
from . import (
    appointments as appointments,
    notices as notices,
    lanes as lanes,
    availability as availability,
    blocked_times as blocked_times,
    series as series,
    settings as settings,
    access as access,
    agenda as agenda,
    booking as booking,
    business as business,
    ownership as ownership,
    reads as reads,
    recovery as recovery,
)
