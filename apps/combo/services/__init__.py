"""Write operations of the combo app: one operation = one transaction, with its events in the outbox.

Only the fields sent change. A new course goes last in its menu and a new choice last in its course;
``reorder`` takes the whole list and saves it at once. Creating a course locks its menu and creating a
choice locks its course (``select_for_update``), so two people adding the same name or product at once
get one row and a 409, and the caps (20 courses, 40 choices) hold; the unique constraints are the last
net. A product must be live, active and sold by units in Inventory to become a choice. A write holds the
product or tax category it names until it commits (``held``, FOR KEY SHARE): a deletion waits for it, and
one already under way is read once it ends, gone, as one deleted before (a 422 on the field, never a 500).
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    on_sale as on_sale,
    menus as menus,
    courses as courses,
    choices as choices,
    writes as writes,
)
