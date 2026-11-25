"""Read operations of the table app (``READ ONLY``): the zones, the live floor, the checks of the room,
the waiters, the setup status and the settings.

A table's status is computed here, never stored: **occupied** when it has a live check (open, with its
check of Sales still open or without one), else **blocked** when it is out of service, else
**reserved** when a live hold is already within its window (from ``RESERVED_LEAD`` before it starts
until it ends), else **available**. A check of Sales charged in full or voided is read here, so the plan
and the list of checks are right on every read, before the relay delivers what Sales did (WORKBOOK
«Para quien lo mantiene»). services.py reuses the same helpers inside its own transaction.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break. The ``find_*`` helpers resolve
how a person names a record (assistant, voice): by id, else an exact name or number, else the only one
that contains it; several → 409 ``*_ambiguous`` naming them.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    zones as zones,
    tables as tables,
    sessions as sessions,
    waiters as waiters,
    floor_plan as floor_plan,
    settings as settings,
    holds as holds,
    floor as floor,
    lookups as lookups,
    paging as paging,
)
