"""Write operations of the task app: one operation = one transaction, with its events in the outbox.

A write on a task locks its row (``select_for_update``) before it looks at its status, so two people
completing it at once are queued and the second one sees the first one's work. A write that names a
person (an assignee, a project's owner) holds their staff record first, before the task or the project:
the Hub admin's «Delete» of a person takes the record and then clears what names it, so it waits for the
write, or the write waits for it and hears the person is gone. A task the caller does
not see does not exist for them (404); one they see but may not change is a 403. Refusals about a field
carry it, so the screen puts them next to it. Nothing fails in silence: a refused create writes nothing
and spends no number.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the helpers follow.
from . import (
    tasks as tasks,
    reactions as reactions,
    comments as comments,
    projects as projects,
    writes as writes,
)
