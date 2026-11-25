"""Read operations of the task app (``READ ONLY``), and the loaders services/ reuses.

Who sees what: a caller with ``task.view_all`` sees every task; anyone else, their own — the ones
assigned to their staff record (the one linked to their account) and the ones they created. A task the
caller does not see does not exist for them (404, never 403). «Today» is the business's day
(``business_today``, on the clock of ``base.business.business_zone``). A task may be named by its id, its
number or its title, a project by its id, its code or its name: the assistant speaks names.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    tasks as tasks,
    comments as comments,
    projects as projects,
    reads as reads,
)
