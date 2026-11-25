"""Write operations of the tax app: one operation = one transaction, with its events in the outbox.

A rule is never edited nor deleted: it is created, given an end date, deactivated or reactivated.
Every write that can make two active root rules of the same slot (country, region, category) apply on
the same day locks the category's row first (``select_for_update``), so two people saving at once are
queued, and the second one's check sees the first one's rule. The refusals carry the
field they are about, so the screen puts them next to it.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    categories as categories,
    aliases as aliases,
    rules as rules,
    rule_lifecycle as rule_lifecycle,
    settings as settings,
    overlaps as overlaps,
)
