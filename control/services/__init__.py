"""Control's commands: the database clusters the hubs' databases are on.

The Hub admin (``control.admin_clusters``) registers, edits, closes and deletes a cluster only through these
operations, for the platform's admins (staff and superuser, ``platform_admin``) or the platform itself; support only
reads. Each runs on control (the registry's scope) and records its event in control's outbox in the same transaction.

- A cluster with a ``secret_name`` is saved only once its app's secret (``<secret_name>/app``) resolves through
  ``base.tenancy.credentials.credentials_for``: the web, where the admin runs, may read only that one, so the
  migrator's is never asked from here (the worker and ``hub-migrate`` read it when they first reach the cluster).
- «Close to new hubs» (``control.cluster.close``) takes it out of the placement of new hubs
  (``base.services.provisioning.place_hub``); the hubs on it stay there.
- Its writer (``host``, ``port``) never changes under the hubs on it: another writer is another server, and the way
  there is moving them (``base.hub.move``). Its PgBouncer, limit, secret and name may change.
- A cluster any hub's row still points at (a purged demo's included: the foreign key protects it), a hub is moving to,
  or that still keeps a hub's moved copy, is never deleted.
- ``control.hub.move`` asks the worker to move a ready hub's own database to another cluster (``base.tenancy.move``):
  only to an open one with room (as a new hub is placed, counting the hubs on their way there), and only a database
  that is on its server (``control.queries``). Its size stops nothing: the copy goes through the dumps bucket, never
  the worker's disk. Its host answers 503 «maintenance» until the worker is done.
  Asked for the business's night (``when="at_night"``), nothing closes: the hub keeps the cluster and the moment it
  starts (:func:`night_start`, on the business's own clock), the same checks are made again when the worker starts it
  (:func:`start_scheduled_move`, under the hub's lease), and «Cancel the move» takes it away until then.
- ``control.hub.restore`` asks the worker to put a ready hub's database back as it was at a moment
  (``base.tenancy.restore``): from the copy of it on a temporary cluster (a point-in-time restore of its own, registered
  closed to new hubs, with no hub on it). Its size stops nothing: the copy goes through the dumps bucket, never the
  worker's disk. Its host answers 503 «maintenance» until the worker is done. The worker refuses it, nothing changed, while the hub's database has a
  production VeriFactu record the copy lacks or has otherwise (it reads both with the migrator, which the web does not
  have; it only reads).
- ``control.hub.restore_aside`` asks the worker for a separate copy of a ready hub's database as it was at a moment
  (``base.tenancy.restore``), from the same copy and under the same conditions, made on the hub's
  own cluster as ``<control>_copy_<hex>`` (a ``RestoredCopy`` row): the business is never closed nor changed, so its
  fiscal records stop nothing, and the copy is no business, closed to the app: nothing in it reaches the tax authority.

Each locks the cluster's row first, as the placement does, so a hub placed at the same time is either counted or
placed after.

``control.freeze.set`` freezes the platform for a database upgrade with Blue/Green, or lifts its freeze: while
frozen the worker makes, drops and moves no database and makes no app's tables, and ``migrate_hubs`` refuses to start,
while the relay, the tasks and the sends to the AEAT go on. It is
idempotent: frozen again, the freeze in course is kept as it was (who, since when, why); lifted again, nothing changes.
Only a real change records its event. Its one row is locked first, so two admins at once change it once.
"""

# Importing a module registers its operations: the modules with operations come first, in the order the registry
# lists them, and the worker's steps follow.
from . import (
    actor as actor,
    clusters as clusters,
    move as move,
    restore as restore,
    recover as recover,
    freeze as freeze,
    worker_move as worker_move,
    worker_copy as worker_copy,
    worker_recovery as worker_recovery,
)
