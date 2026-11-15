"""Events of control (``<app>.<entity>.<fact>``): recorded by ``control.services`` in the transaction of their
operation, in control's outbox. The database clusters of the Hub admin:
no live query reacts to them yet; the outbox keeps them as the record of who registered, edited, closed or deleted a
cluster, by its id and name (never its secret's values), who asked a hub to move or to be restored or a
separate copy of it, and who froze the platform for a database upgrade and lifted it.
"""

CLUSTER_CREATED = "control.cluster.created"
CLUSTER_UPDATED = "control.cluster.updated"
#: Closed to new hubs: the ones on it stay where they are.
CLUSTER_CLOSED = "control.cluster.closed"
CLUSTER_DELETED = "control.cluster.deleted"
#: A hub was asked to move to another cluster (``id``, ``slug``, ``from``: its cluster or empty, ``to``); the worker
#: moves it (``base.tenancy.move``).
HUB_MOVE_REQUESTED = "control.hub.move_requested"

#: A hub was asked to move in its next night (``id``, ``slug``, ``from``, ``to``, ``at``: when it starts); open until
#: the worker starts it (``base.tenancy.move.launch_due``).
HUB_MOVE_SCHEDULED = "control.hub.move_scheduled"

#: A move was asked to be undone (``id``, ``slug``); the worker puts the hub back on its origin.
HUB_MOVE_CANCEL_REQUESTED = "control.hub.move_cancel_requested"

#: A move asked for the night was cancelled before it started (``id``, ``slug``, ``to``): nothing was closed.
HUB_SCHEDULED_MOVE_CANCELLED = "control.hub.scheduled_move_cancelled"

#: A hub was asked to be put back as it was at a moment (``id``, ``slug``, ``from``: the temporary cluster its copy is
#: on, ``at``: the moment); the worker restores it (``base.tenancy.restore``).
HUB_RESTORE_REQUESTED = "control.hub.restore_requested"

#: A hub was asked for a separate copy of its database as it was at a moment (``id``: the copy's, ``hub``, ``slug``,
#: ``from``: the temporary cluster, ``at``, ``database``: the copy's name); the worker makes it
#: (``base.tenancy.restore``) and the business is never closed.
HUB_RESTORE_ASIDE_REQUESTED = "control.hub.restore_aside_requested"

#: The staff asked to bring back into a business what one of its separate copies holds and it lacks (``id``: the
#: recovery, ``copy``, ``hub``, ``slug``, ``apps``: the labels asked); the worker does it
#: (``base.tenancy.recovery``), each record created by its app's own operation.
COPY_RECOVERY_REQUESTED = "control.copy.recovery_requested"

#: The platform was frozen for a database upgrade (``reason``): the worker makes, drops and moves no database
#: and ``migrate_hubs`` refuses to start until it is lifted.
FREEZE_STARTED = "control.freeze.started"
#: Its freeze was lifted (``frozen_since``: when it started): what waited is done from the worker's next tick.
FREEZE_LIFTED = "control.freeze.lifted"

ALL = [
    CLUSTER_CREATED,
    CLUSTER_UPDATED,
    CLUSTER_CLOSED,
    CLUSTER_DELETED,
    HUB_MOVE_REQUESTED,
    HUB_MOVE_SCHEDULED,
    HUB_MOVE_CANCEL_REQUESTED,
    HUB_SCHEDULED_MOVE_CANCELLED,
    HUB_RESTORE_REQUESTED,
    HUB_RESTORE_ASIDE_REQUESTED,
    COPY_RECOVERY_REQUESTED,
    FREEZE_STARTED,
    FREEZE_LIFTED,
]
