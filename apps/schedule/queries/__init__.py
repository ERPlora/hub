"""Read operations of the schedule app (``READ ONLY``): the week, the special days, the temporary changes,
the settings, «is it open?» and the hours of a range of days.

The rules are engine.py's: these operations only load the business's rows (``load_calendar``) and hand
them over, so «is it open?» and the appointment book's hours can never disagree. The business's zone is
the Hub's (``base.business.business_zone``).
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them (the week, the lists, the reads by id, the settings, «is it open?» and the hours of a range), and the
# helpers follow.
from . import (
    week as week,
    lists as lists,
    references as references,
    settings as settings,
    is_open as is_open,
    hours as hours,
    rows as rows,
    outputs as outputs,
)
