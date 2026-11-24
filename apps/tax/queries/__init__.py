"""Read operations of the tax app (``READ ONLY``), and the one resolution of a rate.

``resolve_tax`` and ``calculate_tax`` are not operations: they are the single implementation of which
rule applies and of the money arithmetic. ``tax.rate.calculate`` wraps them, and sales and invoice
(which require tax) call them inside their own operation, so what is charged, what is declared and
what the assistant says can never drift apart.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    calculation as calculation,
    categories as categories,
    rules as rules,
    aliases as aliases,
    settings as settings,
    resolution as resolution,
    jurisdiction as jurisdiction,
    naming as naming,
)
