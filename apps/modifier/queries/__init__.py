"""Read operations of the modifier app, and the lookups its writes share.

The lists of the screen (groups, options, links) page by at most 100 with a stable order ending in the
id. The till reads two things (MODIFIER-F06 to F08): the groups of a product, its own and those of all
its live categories, each once; and the valuation of what was chosen, the only door of a supplement's
price. A link to a product or a category Inventory deleted is left out of every read: Inventory
deletes logically, and until its event is delivered (F09) the link is still in the table.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    groups as groups,
    options as options,
    links as links,
    till as till,
    reads as reads,
    recovery as recovery,
    selection as selection,
    copy_columns as copy_columns,
)
