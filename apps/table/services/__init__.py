"""Write operations of the table app: drawing the room (zones, tables), serving it (seating, closing,
moving, joining and splitting the checks of its tables), the holds and the settings.

Each one is one transaction with its events in the outbox. The check of a table is an open check of
Sales: seating opens it (``sale.order.open``) or retitles the one brought (``sale.order.set_label``);
a transfer and a restore retitle it; a merge joins the two checks (``sale.order.merge``); a split
divides it (``sale.order.split``); closing a table whose check is empty voids it (``sale.order.void``, which Sales allows on an empty
check to whoever builds checks).
Sales' operations are called by name, with the caller's own session and inside this transaction: if
Sales refuses, nothing of the table changes either.

Concurrency: a write that seats a check locks the table first (``select_for_update``) and checks it is
still free under the lock, so two waiters seating the same table at once leave one check; a write on a
check locks the check. Before deciding, a write closes the checks whose check of Sales already ended
(``settle``), as the reads already show them, without waiting for the relay.
"""

from . import (
    writes as writes,
    zones as zones,
    tables as tables,
    seating as seating,
    joining as joining,
    check_changes as check_changes,
    holds as holds,
    settings as settings,
)
