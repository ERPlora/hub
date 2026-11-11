"""Events of control (``<app>.<entity>.<fact>``): recorded by ``control.services`` in the transaction of their
operation, in control's outbox. The database clusters of the Hub admin (round 2026-10-30b of PLAN-DB, decision 1):
no live query reacts to them yet; the outbox keeps them as the record of who registered, edited, closed or deleted a
cluster, by its id and name (never its secret's values), who asked a hub to move or to be restored (hub#1198) or a separate copy of it (hub#1213), and who
froze the platform for a database upgrade and lifted it (hub#930).
"""

CLUSTER_CREATED = "control.cluster.created"
CLUSTER_UPDATED = "control.cluster.updated"
#: Closed to new hubs: the ones on it stay where they are.
CLUSTER_CLOSED = "control.cluster.closed"
CLUSTER_DELETED = "control.cluster.deleted"
#: A hub was asked to move to another cluster (``id``, ``slug``, ``from``: its cluster or empty, ``to``); the worker
#: moves it (``base.tenancy.move``).
HUB_MOVE_REQUESTED = "control.hub.move_requested"

#: A move was asked to be undone (``id``, ``slug``); the worker puts the hub back on its origin.
HUB_MOVE_CANCEL_REQUESTED = "control.hub.move_cancel_requested"

#: A hub was asked to be put back as it was at a moment (``id``, ``slug``, ``from``: the temporary cluster its copy is
#: on, ``at``: the moment; hub#1198); the worker restores it (``base.tenancy.restore``).
HUB_RESTORE_REQUESTED = "control.hub.restore_requested"

#: A hub was asked for a separate copy of its database as it was at a moment (``id``: the copy's, ``hub``, ``slug``,
#: ``from``: the temporary cluster, ``at``, ``database``: the copy's name; hub#1213); the worker makes it
#: (``base.tenancy.restore``) and the business is never closed.
HUB_RESTORE_ASIDE_REQUESTED = "control.hub.restore_aside_requested"

#: The platform was frozen for a database upgrade (``reason``; hub#930): the worker makes, drops and moves no database
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
    HUB_MOVE_CANCEL_REQUESTED,
    HUB_RESTORE_REQUESTED,
    HUB_RESTORE_ASIDE_REQUESTED,
    FREEZE_STARTED,
    FREEZE_LIFTED,
]
