"""Read operations of the kitchen app (``READ ONLY``): the board, what is left to cook, the tickets, the
tickets of a check, the stations, the routing, the settings and the history.

The outbox relay delivers Sales' events a moment after its COMMIT (events.py); until the reaction saves
them, the kitchen reads what Sales did (WORKBOOK «A qué reacciona»):

- a round Sales fired that the kitchen has not saved yet is read from Sales' lines (``rounds.pending_rounds``)
  and shown as a ticket «not saved yet» (``saved = False``), with the id of its first line, the number
  it will have and its dishes routed by today's routing; the first write of the kitchen saves it
  (services.settle);
- what Sales did after (a line voided, the check voided or charged) is applied when read by
  ``state.effective`` (KITCHEN-F27, F28, F29), without writing; services.settle applies the same function
  and saves its changes with their History.

services.py reuses these helpers inside its own transaction. Every list pages (``limit`` ≤ 100) with
``id`` as the last tie-break. ``find_*`` resolve how a person names a record (assistant, voice): by id,
else a number or an exact name, else the only one that contains it; several → 409 ``*_ambiguous``.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (the board, the tickets, the stations and the routing, the settings, the history), and the helpers follow.
from . import (
    board as board,
    tickets as tickets,
    stations as stations,
    settings as settings,
    history as history,
    outputs as outputs,
    reads as reads,
    rounds as rounds,
    routing as routing,
    scope as scope,
    state as state,
    views as views,
)
