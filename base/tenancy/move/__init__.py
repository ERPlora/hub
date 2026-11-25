"""A hub's database moved to another cluster.

The Hub admin asks (``control.hub.move``: ``Hub.moving_to``; its host answers 503 «maintenance» from then on,
``base.registry``); the worker moves it here (:func:`run_due`, in its own thread), one hub at a time, under the hub's
lease (``hub_due``, provisioning's: :data:`LEASE`, renewed while it copies). A database of any size moves: its copy
goes through the dumps bucket (``base.tenancy.dumps``), never through a file of the worker, with the business in
maintenance for as long as it takes (:data:`COPY_TIMEOUT_SECONDS` for each half). Without a bucket nothing is closed and
the move ends there, with why. A move asked for the business's night is started by the same pass first
(:func:`launch_due`), under the same lease, once it is night on the business's own clock; the pass then moves it as any
other.

1. **Closed.** On the origin (its cluster, or the settings' own server), ``CONNECT`` and ``TEMPORARY`` are taken from
   the environment's ``hub_app`` and ``hub_admin`` (``base.tenancy.ops.environment_roles``) and every other session on
   it is ended: nothing writes in it from here on (in AWS, PgBouncer's server connections are ended too and cannot come
   back).
2. **Renamed** ``<control>_move_<hex>`` (``base.tenancy.names``): the copy it leaves behind, noted in control first
   (``MovedCopy`` without ``moved_at``: the hub's data is in it while the move goes on). An older copy of the same hub
   on that server (an earlier move off it) gives way first. Renaming before the destination is made frees the name on
   the origin's server, so a move between two clusters of one server works as any other (the tests' too): where the
   data is comes from control's note, never from which names a server holds.
3. **Copied**: ``pg_dump`` of the copy sent to the dumps bucket as it is made (``dumps.stream_to_bucket``: the
   migrator's direct connection; ``<hex>/<AAAAMMDDTHHMMSSZ>-move.dump``, kept the bucket's 90 days and listed to
   nobody), and on the destination a new database cloned from that cluster's template of the hub's vertical
   (``ops.clone_database``: private, open to the app's roles), emptied of the template's tables and filled with
   ``pg_restore`` in one transaction, reading the copy from the bucket on its input. The template's extensions stay:
   the restore leaves them out (on Aurora only the master makes ``vector``).
4. **Checked**: its identity (``base_hub_identity``) says it is this hub, and its schema is brought to the code's leaf
   (``migrator.schema.ensure_schema``).
5. **Switched**: control moves the hub to the destination and keeps the copy's row (``MovedCopy``) in one transaction.
   From then on every process reaches it there: a request, a live re-run and the worker read the row again and
   register the hub's alias anew when its server changed (``base.tenancy.connections``).

Every step that drops, renames or switches first checks that the move is still this worker's: it holds the hub's lease
(renewed by then) and the hub still moves to its destination, unasked to be undone (``control.services.worker_move.still_ours``;
the switch checks it again on its locked row). A worker whose lease ran out (each deploy starts the new one before the
old one stops) thus never drops a destination another worker made live, nor switches a move another one finished; it
stops, as one that is stopping or whose lease went elsewhere does, and leaves everything to whoever holds it now.

Any failure before the switch puts the hub back on its origin, nothing lost, starting with the origin: the copy is
renamed back (after the destination's database is dropped, when it answers: by then it is never the live one) and
opened to the app again, the origin's schema record given back to control, the hub ready there with the reason in
``last_error`` (``move_<step>: <why>``). A destination that does not answer is noted (``LeftoverDatabase``) and its
database dropped on a later pass, under the hub's lease, never while control says it is a hub's (one on that cluster,
moving to it, or living on the same server). An undo that cannot finish leaves the hub moving and says why; the next
pass undoes it again, never taking it forward. Asked to cancel (``control.hub.move_cancel``), the next pass undoes it
the same way.

The copies are dropped after :data:`MOVED_COPY_DAYS` (:func:`drop_old_copies`, in the same pass), with their rows;
one that cannot be dropped now is tried again on the next pass. A restore's kept copies go the same way.

Its steps are a restore's too (``base.tenancy.restore``): the same move with its origin and destination the
other way round, the copy coming from a temporary cluster and the hub staying on its own, through the bucket the same
way (:func:`_dump_to_bucket`, :func:`_restore_from_bucket`).

Every name is validated by ``base.tenancy.names`` and reaches SQL as ``sql.Identifier``; control is written through
``control.services`` only (its doors to the ORM).

Each part lives in a module of its own, imported here: ``worker_pass`` (the worker's pass: :func:`run_due`, the
moves asked for a night, the copies past their days and the leftovers), ``moving`` (one hub's move and its undoing
when a step fails), ``closing`` (steps 1 and 2, on the origin), ``bucket`` (step 3's copy through the dumps bucket
and its time limit), ``destination`` (steps 3 and 4 on the destination), ``undo`` (the hub back on its origin),
``databases`` (what a move runs on a server's databases) and ``exceptions`` (what its steps raise).
"""

from . import (
    bucket as bucket,
    closing as closing,
    databases as databases,
    destination as destination,
    exceptions as exceptions,
    moving as moving,
    undo as undo,
    worker_pass as worker_pass,
)
