"""Events of control (``<app>.<entity>.<fact>``): recorded by ``control.services`` in the transaction of their
operation, in control's outbox. The database clusters of the Hub admin (round 2026-10-30b of PLAN-DB, decision 1):
no live query reacts to them yet; the outbox keeps them as the record of who registered, edited, closed or deleted a
cluster, by its id and name (never its secret's values), and who asked a hub to move.
"""

CLUSTER_CREATED = "control.cluster.created"
CLUSTER_UPDATED = "control.cluster.updated"
#: Closed to new hubs: the ones on it stay where they are.
CLUSTER_CLOSED = "control.cluster.closed"
CLUSTER_DELETED = "control.cluster.deleted"
#: A hub was asked to move to another cluster (``id``, ``slug``, ``from``: its cluster or empty, ``to``); the worker
#: moves it (``base.tenancy.move``).
HUB_MOVE_REQUESTED = "control.hub.move_requested"

ALL = [CLUSTER_CREATED, CLUSTER_UPDATED, CLUSTER_CLOSED, CLUSTER_DELETED, HUB_MOVE_REQUESTED]
