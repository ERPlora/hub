"""Read operations of the cash register app (``READ ONLY``) and the helpers the writes share with them.

The sale lines of a shift are **read from sale** (its requirement: ``Sale``, ``SalePayment``,
``RefundPayment``) at the moment of looking, by their time: a charge belongs to the shift open when it
was charged, a void to the shift open when it was voided, a refund to the shift open when it was given.
A closed session reads only its own copies (``Movement``), made when it closed, so it never moves again.
What fell in no session (with the drawer closed, after a forgotten shift's cut-off, or confirmed while a
shift was closing) is the «unassigned» lines. The close's summary (``session.closing_summary``) reads the shift review
of other apps by their operations' names (Sales' open checks, Kitchen's board, Printing's queue), as the person.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (settings, drawers, sessions, the close, movements, counts, currency), and the helpers follow.
from . import (
    settings as settings,
    registers as registers,
    sessions as sessions,
    closing as closing,
    movements as movements,
    counts as counts,
    currency as currency,
    auto_close as auto_close,
    figures as figures,
    lines as lines,
    ownership as ownership,
    people as people,
    unassigned as unassigned,
)
