"""Live queries of the cash register app and the events that re-run them after the COMMIT.

Sale's charges, voids and refunds re-run everything that shows the open shift: its lines are read from
sale when the query runs, so a cash sale is in the drawer as soon as it is charged.
"""

from live.live_registry import live

from apps.cash_register import events as E

SHIFT = [
    E.SESSION_OPENED,
    E.SESSION_CLOSED,
    E.MOVEMENT_ADDED,
    *E.SALE_EVENTS,
]

live("cash_register.settings.get", on=[E.SETTINGS_UPDATED])
live("cash_register.register.list", on=[E.REGISTER_CREATED, E.REGISTER_UPDATED])
# The blind count decides who reads the expected; a drawer's name is shown on its sessions. The Home's panels follow
# the same events (apps.py).
live("cash_register.session.list", on=E.SESSION_EVENTS)
live(
    "cash_register.session.current", on=[*SHIFT, E.SETTINGS_UPDATED, E.REGISTER_UPDATED]
)
live(
    "cash_register.session.get",
    on=[*SHIFT, E.COUNT_ADDED, E.SETTINGS_UPDATED, E.REGISTER_UPDATED],
)
# The close's summary: its cash figures; what it reads of Sales, Kitchen and Printing is read when it runs.
live(
    "cash_register.session.closing_summary",
    on=[*SHIFT, E.SETTINGS_UPDATED, E.REGISTER_UPDATED],
)
# A session's lines, and the unassigned ones (which an opening or a closing moves).
live("cash_register.movement.list", on=SHIFT)
live("cash_register.count.list", on=[E.COUNT_ADDED])
live("cash_register.currency.get", on=[E.SETTINGS_UPDATED])
