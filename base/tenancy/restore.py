"""A hub's database put back as it was at a moment, from a copy on a temporary cluster (hub#1198; PLAN-DB §13
«Restaurar un hub»).

The move's shape (``base.tenancy.move``, whose steps it uses) with its origin and destination the other way round: the
copy comes from a cluster made for it (a point-in-time restore of the hub's own, registered in the Hub admin closed to
new hubs, its secrets ``erplora/<env>/clusters/<name>/{app,migrator}``), and the hub stays on its own cluster. The Hub
admin asks (``control.hub.restore``: ``Hub.restoring_from`` and ``restore_point``; its host answers 503 «maintenance»
from then on, ``base.registry``); the worker restores it here (:func:`run_due`, in the moves' thread), one hub at a
time, under the hub's lease (``hub_due``, provisioning's: ``move.LEASE``, renewed while it copies).

1. **Copied**: ``pg_dump`` of the hub's database on the temporary cluster (:func:`source_name`; nobody uses it), before
   the business is closed.
2. **Checked, fiscal**: every app whose records reach the tax authority answers what each of them says in its database
   and in the copy (``fiscal_record_states`` on its ``LiveAppConfig``, through a direct connection: both are closed to
   the app and the copy has no alias), and the answers are compared: a record the copy lacks (made after the moment)
   or has otherwise (sent, answered or changed after it) stops the restore, nothing changed and the business never
   closed. Putting the copy in its place would repeat numbers the tax authority has and drop invoices the business
   must keep. The copy itself says what it holds, whatever moment was given. It only reads: nothing fiscal is changed
   or sent.
3. **Closed**: its own database is closed to the app as a move closes its origin (``CONNECT`` and ``TEMPORARY`` taken
   from the environment's ``hub_app`` and ``hub_admin``, every other session ended): nothing writes in it from here on.
   The fiscal check is repeated then: the business could invoice until it was closed (it is opened again if it stops).
4. **Kept**: renamed ``<control>_old_<hex>`` (``names.kept_db_name``, a UUIDv7 of its own), noted in control first
   (``MovedCopy`` without ``moved_at``: the hub's data is in it while the restore goes on).
5. **Made**: a new database of its name on its own cluster, cloned from its vertical's template there, emptied of the
   template's tables (only while the kept copy is there with its note: what has the hub's name then is never its data)
   and closed to the app until the end; filled with the copy's ``pg_restore`` in one transaction; its identity
   (``base_hub_identity``) checked and its schema brought to the code's leaf (``migrator.ensure_schema``: it learns the
   apps the copy has).
6. **Ended**: opened to the app, and control ends the restore and dates the kept copy in one transaction.

Every step that drops, renames or ends first checks that the restore is still this worker's: it holds the hub's lease
and the hub is still restored from that cluster, unasked to be undone (``control.services.still_restoring``; the end
checks it again on its locked row). A worker whose lease ran out leaves everything to whoever holds it now.

Any failure before the end puts the hub's own database back, nothing lost: the new one dropped (only while the kept copy
is there with its note), the kept copy renamed back and opened to the app again, the schema record of before given back
to control, the hub ready with the reason in ``last_error`` (``restore_<step>: <why>``). An undo that cannot finish
leaves the hub restoring, closed, and says why; the next pass undoes it again, never taking it forward. The kept copies
are dropped after ``move.MOVED_COPY_DAYS`` by the moves' pass (``move.drop_old_copies``), with their rows.
"""

import datetime as dt
import logging
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

import psycopg
from django.utils import timezone
from live.meta import all_live_app_configs

from base import services
from base.tenancy import bootstrap, dumps, move, names, ops
from base.tenancy import connections as tenancy_connections
from control import services as control_services

logger = logging.getLogger(__name__)

#: The worker's lease of a hub being restored: the move's (provisioning's), renewed while it copies.
LEASE = move.LEASE
#: What ``last_error`` says after the reason of a restore that could not be undone yet.
UNDO_FAILED_MARK = " (restore_undo_failed: "


def source_name(hub) -> str:
    """The name of ``hub``'s copy on its temporary cluster: its own, as a restore of the whole cluster keeps it."""
    return hub.db_name


def run_due(
    now: dt.datetime | None = None,
    *,
    roles: bootstrap.Names | None = None,
    cancelled: Callable[[], bool] | None = None,
    source: Callable[[object], str] = source_name,
) -> int:
    """The worker's pass: restore the hub asked longest ago whose lease nobody else holds (one a pass: a copy takes a
    while); how many it worked on. ``roles``: the app's roles its database is closed to (default the environment's);
    ``cancelled``: whether the worker is stopping; ``source``: where each hub's copy is on its temporary cluster."""
    now = now or timezone.now()
    for hub_id in control_services.hubs_restoring():
        # By the clock, never ``now``: a move before it in the same tick may have taken longer than the lease.
        if services.claim_hub(hub_id, timezone.now(), LEASE) is None:
            continue
        try:
            restore_hub(hub_id, now=now, roles=roles, cancelled=cancelled, source=source)
        finally:
            services.release_hub(hub_id, timezone.now())
        return 1
    return 0


def restore_hub(
    hub_id,
    *,
    now: dt.datetime | None = None,
    roles: bootstrap.Names | None = None,
    cancelled: Callable[[], bool] | None = None,
    source: Callable[[object], str] = source_name,
) -> None:
    """Put ``hub_id``'s database back from its copy, or undo its restore when it is to be undone, its lease held (see
    the module); a failure is undone and noted on it, never raised."""
    now = now or timezone.now()
    hub = control_services.moving_row(hub_id)
    if hub is None or hub.restoring_from is None:
        return
    control = tenancy_connections.control_name()
    roles = ops.environment_roles(control) if roles is None else roles
    origin = hub.restoring_from
    note = control_services.pending_copy(hub.id)
    kept_name = note.db_name if note is not None else names.kept_db_name(control, uuid.uuid7())

    def heartbeat() -> None:
        services.renew_lease(hub.id, LEASE)

    def ours(*, forward: bool = True) -> None:
        heartbeat()
        try:
            control_services.still_restoring(hub.id, origin.pk, services.LEASE_OWNER, forward=forward)
        except control_services.MoveTaken as taken:
            raise move.MoveStopped(str(taken)) from taken

    try:
        if hub.move_undo_asked_at is not None:
            reason = hub.last_error.split(UNDO_FAILED_MARK)[0] or "restore_cancelled: it was asked to be undone"
            _back(hub, kept_name, roles, ours, reason=reason)
            return
        try:
            with tempfile.TemporaryDirectory(prefix="hub-restore-") as folder:
                path = Path(folder) / "restore.dump"
                copy = source(hub)
                move._dump(copy, origin, path, ours, cancelled)
                _close_and_keep(hub, kept_name, roles, ours, copy, origin)
                _make_new(hub, kept_name, roles, ours)
                move._restore(path, hub.db_name, hub.cluster, ours, cancelled)
            heartbeat()
            move._verify_identity(hub.db_name, hub.cluster, hub.id)
            move._ensure_schema(hub, hub.cluster, heartbeat)
            _finish(hub, origin, kept_name, roles, ours, now)
        except (services.ProvisioningStopped, move.MoveStopped, dumps.DumpStopped) as stopped:
            logger.info("base.tenancy.restore.stopped hub=%s: %s; left to whoever holds it now.", hub.slug, stopped)
            return
        except Exception as error:
            reason = _reason(error)
            logger.warning("base.tenancy.restore.failed hub=%s: %s", hub.slug, reason)
            _back(hub, kept_name, roles, ours, reason=reason)
            return
        logger.info("base.tenancy.restore.restored hub=%s database=%s kept=%s", hub.slug, hub.db_name, kept_name)
    finally:
        move._close_this_processs(hub)


def _reason(error: Exception) -> str:
    """Why a restore failed, as ``last_error`` says it: ``restore_<step>: <why>``, a step of the move's own included."""
    if not isinstance(error, move.MoveFailed):
        return f"restore_unexpected: {type(error).__name__}: {error}"
    code = error.code
    if code.startswith("move_"):
        code = f"restore_{code.removeprefix('move_')}"
    return f"{code}: {str(error).split(': ', 1)[1]}"


def _back(hub, kept_name: str, roles, ours, *, reason: str) -> None:
    """Undo the restore of ``hub`` and note why; one that cannot be undone now stays restoring, undone next time."""
    try:
        _put_back(hub, kept_name, roles, ours)
    except (services.ProvisioningStopped, move.MoveStopped) as stopped:
        logger.info("base.tenancy.restore.stopped hub=%s: %s; left to whoever holds it now.", hub.slug, stopped)
        return
    except Exception as undo_error:
        logger.exception("base.tenancy.restore.undo_failed hub=%s: it stays restoring, undone next time.", hub.slug)
        control_services.move_stuck(hub.id, f"{reason}{UNDO_FAILED_MARK}{type(undo_error).__name__}: {undo_error})")
        return
    control_services.move_undone(hub.id, hub.cluster_id, kept_name, reason)
    logger.info("base.tenancy.restore.undone hub=%s: %s", hub.slug, reason)


# ── The steps ────────────────────────────────────────────────────────────────────────────────────────────────────────


def _close_and_keep(hub, kept_name: str, roles: bootstrap.Names, ours, copy: str, origin) -> None:
    """Steps 2 to 4 on the hub's cluster: its fiscal records compared with the copy's, its database closed to the app
    and compared again, then noted (with its schema record) and renamed to its kept copy. A restore cut after its
    rename (its kept copy noted and there) goes on from the kept copy; without the hub's database or such a copy, there
    is nothing to keep."""
    name, cluster = hub.db_name, hub.cluster
    try:
        with ops.connect_ops(cluster=cluster) as conn:
            present = move._present(conn, name, kept_name)
        kept_already = control_services.pending_copy(hub.id) is not None and kept_name in present
        if not kept_already and name not in present:
            raise move.MoveFailed("restore_database_missing", f"{name} is not on its cluster")
        live = kept_name if kept_already else name
        _refuse_fiscal_changes(live, cluster, copy, origin)
        with ops.connect_ops(cluster=cluster) as conn:
            ours()
            move._close(conn, live, roles)
        _refuse_fiscal_changes(live, cluster, copy, origin)
        if kept_already:
            return
        control_services.copy_pending(
            hub.id, getattr(cluster, "pk", None), kept_name, schema_state=hub.schema_state, schema_apps=hub.schema_apps
        )
        with ops.connect_ops(cluster=cluster) as conn:
            ours()
            move._rename(conn, name, kept_name)
    except psycopg.Error as error:
        raise move.MoveFailed("restore_close_failed", ops.reason(error)) from error
    except ops.DatabaseOpsError as error:
        raise move.MoveFailed("restore_close_failed", error) from error


def _make_new(hub, kept_name: str, roles: bootstrap.Names, ours) -> None:
    """Step 5 on the hub's cluster: a new database of its name, cloned from its vertical's template and emptied, closed
    to the app until the end. Only while its kept copy is there with its note: what has the hub's name then is never its
    data (``restore_copy_missing`` otherwise, and it is put back)."""
    ours()
    with ops.connect_ops(cluster=hub.cluster) as conn:
        kept = control_services.pending_copy(hub.id) is not None and kept_name in move._present(conn, kept_name)
    if not kept:
        raise move.MoveFailed("restore_copy_missing", f"{hub.db_name} was not kept aside as {kept_name}: none is made")
    move._clone_emptied(hub, hub.cluster, roles)
    with ops.connect_ops(cluster=hub.cluster) as conn:
        move._close(conn, hub.db_name, roles)


def _finish(hub, origin, kept_name: str, roles: bootstrap.Names, ours, now: dt.datetime) -> None:
    """Step 6: the new database opened to the app, then control ends the restore and dates the kept copy, in one
    transaction on its locked row, only if the restore is still this worker's (``MoveStopped`` otherwise)."""
    ours()
    with ops.connect_ops(cluster=hub.cluster) as conn:
        move._open(conn, hub.db_name, roles)
    try:
        control_services.restore_finished(
            hub.id, origin.pk, hub.cluster_id, kept_name, now, owner=services.LEASE_OWNER
        )
    except control_services.MoveTaken as taken:
        raise move.MoveStopped(str(taken)) from taken


def _put_back(hub, kept_name: str, roles: bootstrap.Names, ours) -> None:
    """Its own database back, as it was. Only the worker's note says the data is in the kept copy (it is written before
    the rename): then what has the hub's name is dropped and the kept copy renamed back. Without the note, the data
    never left: its database is opened to the app again when it is there."""
    ours(forward=False)
    noted = control_services.pending_copy(hub.id) is not None
    with ops.connect_ops(cluster=hub.cluster) as conn:
        present = move._present(conn, hub.db_name, kept_name)
    if noted and kept_name in present:
        if hub.db_name in present:
            ours(forward=False)
            ops.drop_database(hub.db_name, cluster=hub.cluster)
        ours(forward=False)
        move._rename_back(hub.cluster, kept_name, hub.db_name)
    with ops.connect_ops(cluster=hub.cluster) as conn:
        if hub.db_name in move._present(conn, hub.db_name):
            move._open(conn, hub.db_name, roles)


# ── The fiscal guard: it only reads ──────────────────────────────────────────────────────────────────────────────────


def _fiscal_records(name: str, cluster) -> dict:
    """What each record of the database ``name`` on ``cluster`` that reaches the tax authority says, by its app and
    id, as every app that keeps such records answers it (``fiscal_record_states``); none when no app does."""
    asking = [
        (config.label, ask)
        for config in all_live_app_configs()
        if (ask := getattr(config, "fiscal_record_states", None)) is not None
    ]
    if not asking:
        return {}
    with ops.connect_ops(name, cluster=cluster) as conn:
        return {(label, record): state for label, ask in asking for record, state in ask(conn).items()}


def _refuse_fiscal_changes(name: str, cluster, copy: str, origin) -> None:
    """Step 2: ``restore_fiscal_records`` when a record of ``name`` that reaches the tax authority is not, as it is,
    in the copy."""
    try:
        now = _fiscal_records(name, cluster)
        if not now:
            return
        then = _fiscal_records(copy, origin)
    except (psycopg.Error, ops.DatabaseOpsError) as error:
        raise move.MoveFailed("restore_fiscal_unread", f"its fiscal records could not be read: {error}") from error
    changed = sum(1 for record, state in now.items() if then.get(record) != state)
    if changed:
        raise move.MoveFailed(
            "restore_fiscal_records",
            f"fiscal records made, sent or changed after the copy: {changed}; restoring it would repeat numbers the "
            "tax authority already has",
        )

