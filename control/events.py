"""Events of control (``<app>.<entity>.<fact>``): recorded by ``control.services`` in the transaction of their
operation, in control's outbox. The database clusters of the Hub admin (round 2026-10-30b of PLAN-DB, decision 1):
no live query reacts to them yet; the outbox keeps them as the record of who registered, edited, closed or deleted a
cluster, by its id and name (never its secret's values).
"""

CLUSTER_CREATED = "control.cluster.created"
CLUSTER_UPDATED = "control.cluster.updated"
#: Closed to new hubs: the ones on it stay where they are.
CLUSTER_CLOSED = "control.cluster.closed"
CLUSTER_DELETED = "control.cluster.deleted"

ALL = [CLUSTER_CREATED, CLUSTER_UPDATED, CLUSTER_CLOSED, CLUSTER_DELETED]
