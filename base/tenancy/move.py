"""A hub's database moved to another cluster (round 2026-10-30b of PLAN-DB, decision 3; tranche S7, part 1).

The Hub admin asks (``control.hub.move``: ``Hub.moving_to``; its host answers 503 «maintenance» from then on,
``base.registry``); the worker moves it here (:func:`run_due`, in its own thread), one hub at a time, under the hub's
lease (``hub_due``, provisioning's: :data:`LEASE`, renewed while it copies). Only a database small enough for a copy
gets here (``control.services.MOVE_MAX_BYTES``); a larger one needs logical replication, which the Hub does not do yet.

1. **Closed.** On the origin (its cluster, or the settings' own server), ``CONNECT`` and ``TEMPORARY`` are taken from
   the environment's ``hub_app`` and ``hub_admin`` (``base.tenancy.ops.environment_roles``) and every other session on
   it is ended: nothing writes in it from here on (in AWS, PgBouncer's server connections are ended too and cannot come
   back).
2. **Renamed** ``<control>_move_<hex>`` (``base.tenancy.names``): the copy it leaves behind, noted in control first
   (``MovedCopy`` without ``moved_at``: the hub's data is in it while the move goes on). An older copy of the same hub
   on that server (an earlier move off it) gives way first. Renaming before the destination is made frees the name on
   the origin's server, so a move between two clusters of one server works as any other (the tests' too): where the
   data is comes from control's note, never from which names a server holds.
3. **Copied**: ``pg_dump`` of the copy (``base.tenancy.dumps``' own run: the migrator's direct connection), and on the
   destination a new database cloned from that cluster's template of the hub's vertical
   (``ops.clone_database``: private, open to the app's roles), emptied of the template's tables and filled with
   ``pg_restore`` in one transaction. The template's extensions stay: the restore leaves them out (on Aurora only the
   master makes ``vector``).
4. **Checked**: its identity (``base_hub_identity``) says it is this hub, and its schema is brought to the code's leaf
   (``migrator.ensure_schema``).
5. **Switched**: control moves the hub to the destination and keeps the copy's row (``MovedCopy``) in one transaction.
   From then on every process reaches it there: a request, a live re-run and the worker read the row again and
   register the hub's alias anew when its server changed (``base.tenancy.connections``).

Every step that drops, renames or switches first checks that the move is still this worker's: it holds the hub's lease
(renewed by then) and the hub still moves to its destination, unasked to be undone (``control.services.still_ours``;
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
one that cannot be dropped now is tried again on the next pass.

Every name is validated by ``base.tenancy.names`` and reaches SQL as ``sql.Identifier``; control is written through
``control.services`` only (its doors to the ORM).
"""

import copy as copying
import datetime as dt
import logging
import os
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import psycopg
from django.conf import settings
from django.utils import timezone
from psycopg import errors, sql
from psycopg.conninfo import make_conninfo

from base import services
from base.tenancy import bootstrap, dumps, migrator, names, ops, provision
from base.tenancy import connections as tenancy_connections
from control import services as control_services

logger = logging.getLogger(__name__)

#: The worker's lease of a moving hub: provisioning's, renewed while it copies.
LEASE = provision.LEASE
#: How long the copy a hub leaves behind is kept before it is dropped.
MOVED_COPY_DAYS = 7
#: How long the restore may run before it is stopped (the dump has its own, ``dumps.DUMP_TIMEOUT_SECONDS``).
RESTORE_TIMEOUT_SECONDS = dumps.DUMP_TIMEOUT_SECONDS
#: How many times the rename waits for a session that came back to the origin before it gives up.
RENAME_WAITS = (0.5, 1.0)
#: The entries of a dump the restore leaves out: the destination's template has its extensions already, and the public
#: schema is the database's own (dropping it would take the extensions' objects with it).
SKIPPED_ENTRIES = (" EXTENSION ", " COMMENT - EXTENSION ", " SCHEMA - public ", " COMMENT - SCHEMA public ")
#: The lines of ``pg_restore``'s own complaint kept in a failure.
ERROR_LINES = 3


class MoveFailed(RuntimeError):
    """A step of a move that failed: its code (``move_<step>``) and why, in a line."""

    def __init__(self, code: str, reason: object) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code


class MoveStopped(RuntimeError):
    """The worker is stopping: the move is left as it is for the next one to go on."""


def run_due(
    now: dt.datetime | None = None,
    *,
    roles: bootstrap.Names | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    """The worker's pass: move the hub asked longest ago whose lease nobody else holds (one a pass: a copy takes a
    while), then drop the copies past their days; how many hubs it worked on. ``roles``: the app's roles the origin is
    closed to (default the environment's); ``cancelled``: whether the worker is stopping."""
    now = now or timezone.now()
    worked = 0
    for hub_id in control_services.hubs_moving():
        if services.claim_hub(hub_id, now, LEASE) is None:
            continue
        try:
            move_hub(hub_id, now=now, roles=roles, cancelled=cancelled)
            worked = 1
        finally:
            services.release_hub(hub_id, timezone.now())
        break
    drop_old_copies(now)
    drop_leftovers(now)
    return worked


#: What ``last_error`` says after the reason of a move that could not be undone yet.
UNDO_FAILED_MARK = " (move_undo_failed: "


def move_hub(
    hub_id,
    *,
    now: dt.datetime | None = None,
    roles: bootstrap.Names | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> None:
    """Move ``hub_id`` to the cluster it is moving to, or undo its move when it is to be undone, its lease held (see the
    module); a failure is undone and noted on it, never raised."""
    now = now or timezone.now()
    hub = control_services.moving_row(hub_id)
    if hub is None or hub.moving_to is None:
        return
    control = tenancy_connections.control_name()
    copy_name = names.moved_db_name(control, hub.id)
    roles = ops.environment_roles(control) if roles is None else roles
    origin, target = hub.cluster, hub.moving_to

    def heartbeat() -> None:
        services.renew_lease(hub.id, LEASE)

    def ours(*, forward: bool = True) -> None:
        heartbeat()
        try:
            control_services.still_ours(hub.id, target.pk, services.LEASE_OWNER, forward=forward)
        except control_services.MoveTaken as taken:
            raise MoveStopped(str(taken)) from taken

    back = {"hub": hub, "copy_name": copy_name, "origin": origin, "target": target, "roles": roles, "now": now}
    try:
        if hub.move_undo_asked_at is not None:
            reason = hub.last_error.split(UNDO_FAILED_MARK)[0] or "move_cancelled: the move was asked to be undone"
            _back(**back, ours=ours, reason=reason)
            return
        try:
            _close_and_rename(hub, copy_name, origin, roles, ours)
            with tempfile.TemporaryDirectory(prefix="hub-move-") as folder:
                path = Path(folder) / "move.dump"
                # Their heartbeat checks the move is still this worker's: a cancel or a lease lost stops them.
                _dump(copy_name, origin, path, ours, cancelled)
                _make_destination(hub, target, roles, ours)
                _restore(path, hub.db_name, target, ours, cancelled)
            heartbeat()
            _verify_identity(hub.db_name, target, hub.id)
            _ensure_schema(hub, target, heartbeat)
            _switch(hub.id, target, origin, copy_name, now)
        except (services.ProvisioningStopped, MoveStopped, dumps.DumpStopped) as stopped:
            logger.info("base.tenancy.move.stopped hub=%s: %s; left to whoever holds it now.", hub.slug, stopped)
            return
        except Exception as error:
            code = error.code if isinstance(error, MoveFailed) else "move_unexpected"
            reason = str(error) if isinstance(error, MoveFailed) else f"{code}: {type(error).__name__}: {error}"
            logger.warning("base.tenancy.move.failed hub=%s: %s", hub.slug, reason)
            _back(**back, ours=ours, reason=reason)
            return
        logger.info(
            "base.tenancy.move.moved hub=%s database=%s to=%s copy=%s", hub.slug, hub.db_name, target.name, copy_name
        )
    finally:
        _close_this_processs(hub)


def _back(hub, copy_name: str, origin, target, roles, now, ours, *, reason: str) -> None:
    """Undo the move of ``hub`` and note why; one that cannot be undone now stays moving, to be undone next time."""
    try:
        copy_kept = _undo(hub, copy_name, origin, target, roles, ours, now)
    except (services.ProvisioningStopped, MoveStopped) as stopped:
        logger.info("base.tenancy.move.stopped hub=%s: %s; left to whoever holds it now.", hub.slug, stopped)
        return
    except Exception as undo_error:
        logger.exception("base.tenancy.move.undo_failed hub=%s: it stays moving and is undone next time.", hub.slug)
        control_services.move_stuck(hub.id, f"{reason}{UNDO_FAILED_MARK}{type(undo_error).__name__}: {undo_error})")
        return
    control_services.move_undone(hub.id, getattr(origin, "pk", None), copy_name, reason, copy_kept=copy_kept)
    logger.info("base.tenancy.move.undone hub=%s: %s", hub.slug, reason)


def drop_old_copies(now: dt.datetime) -> int:
    """Drop the copies left behind more than :data:`MOVED_COPY_DAYS` before ``now``, with their rows; how many. One that
    cannot be dropped now stays, and the next pass tries again."""
    dropped = 0
    for kept in control_services.copies_due(now - dt.timedelta(days=MOVED_COPY_DAYS)):
        try:
            _drop_copy(kept.db_name, kept.cluster)
            control_services.forget_copy(kept.cluster_id, kept.db_name)
        except Exception:
            logger.exception("base.tenancy.move.copy_kept copy=%s: it could not be dropped; tried again.", kept.db_name)
            continue
        dropped += 1
        logger.info("base.tenancy.move.copy_dropped copy=%s", kept.db_name)
    return dropped


def drop_leftovers(now: dt.datetime) -> int:
    """Drop what undone moves may have left on their destinations, with their notes; how many. Never one control says is
    a hub's database there (on that cluster, or of a hub moving to it, whose move drops it before it clones) nor one on
    the hub's own server (a row of another cluster pointing at it): its note is forgotten then. Each under the hub's
    lease, taken on the clock and checked again under it; one that cannot be dropped now stays, and the next pass tries
    again."""
    dropped = 0
    for left in control_services.leftovers():
        if not _leftover_droppable(left.hub, left):
            control_services.forget_leftover(left.cluster_id, left.db_name)
            continue
        if services.claim_hub(left.hub_id, timezone.now(), LEASE) is None:
            continue
        try:
            hub = control_services.moving_row(left.hub_id)
            if hub is None or not _leftover_droppable(hub, left):
                control_services.forget_leftover(left.cluster_id, left.db_name)
                continue
            ops.drop_database(left.db_name, cluster=left.cluster)
            control_services.forget_leftover(left.cluster_id, left.db_name)
            dropped += 1
            logger.info("base.tenancy.move.leftover_dropped database=%s cluster=%s", left.db_name, left.cluster.name)
        except Exception:
            logger.exception("base.tenancy.move.leftover_kept database=%s: it could not be dropped; tried again.", left.db_name)
        finally:
            services.release_hub(left.hub_id, timezone.now())
    return dropped


def _leftover_droppable(hub, left) -> bool:
    return not (
        control_services.attributed(left.cluster_id, left.db_name) or _same_server(hub.cluster, left.cluster)
    )


def _server(cluster) -> tuple[frozenset[str], int]:
    """Who a cluster's row points at (``None``: the settings' own server): the addresses its writer's name resolves to,
    and its port. Two rows that spell one server differently (a name and its address, ``localhost``) are one server."""
    if cluster is None:
        default = settings.DATABASES["default"]
        host, port = str(default["HOST"]), int(default["PORT"])
    else:
        host, port = str(cluster.host), int(cluster.port)
    try:
        addresses = frozenset(found[4][0] for found in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
    except OSError:
        addresses = frozenset({host.lower()})
    return addresses, port


def _same_server(one, other) -> bool:
    (one_addresses, one_port), (other_addresses, other_port) = _server(one), _server(other)
    return one_port == other_port and bool(one_addresses & other_addresses)


# ── The steps ────────────────────────────────────────────────────────────────────────────────────────────────────────


def _identifier(name: str) -> sql.Identifier:
    return names.identifier(name, control=tenancy_connections.control_name())


def _present(conn, *wanted: str) -> set[str]:
    return {row[0] for row in conn.execute("SELECT datname FROM pg_database WHERE datname = ANY(%s)", [list(wanted)])}


def _app_roles(conn, roles: bootstrap.Names) -> list[str]:
    """The environment's app roles the server has (local development and the tests may have none)."""
    wanted = [roles.hub_app, roles.hub_admin]
    present = {row[0] for row in conn.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", [wanted])}
    return [role for role in wanted if role in present]


def _close(conn, name: str, roles: bootstrap.Names) -> None:
    """Take ``name`` from everyone but its owner (the migrator) and end every other session on it."""
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(_identifier(name)))
    granted = _app_roles(conn, roles)
    if granted:
        conn.execute(
            sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM {}").format(
                _identifier(name), sql.SQL(", ").join(map(sql.Identifier, granted))
            )
        )
    conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", [name]
    )


def _open(conn, name: str, roles: bootstrap.Names) -> None:
    """Give ``name`` back to the app's roles (what ``ops.clone_database`` gave it)."""
    granted = _app_roles(conn, roles)
    if granted:
        conn.execute(
            sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                _identifier(name), sql.SQL(", ").join(map(sql.Identifier, granted))
            )
        )


def _rename(conn, old: str, new: str) -> None:
    """``ALTER DATABASE old RENAME TO new``, ending the sessions that came back meanwhile, a few times."""
    statement = sql.SQL("ALTER DATABASE {} RENAME TO {}").format(_identifier(old), _identifier(new))
    for wait in (*RENAME_WAITS, None):
        try:
            conn.execute(statement)
            return
        except errors.ObjectInUse as busy:
            if wait is None:
                raise MoveFailed("move_rename_failed", f"{old} is still in use: {ops.reason(busy)}") from busy
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                [old],
            )
            time.sleep(wait)


def _close_and_rename(hub, copy_name: str, origin, roles: bootstrap.Names, ours) -> None:
    """Steps 1 and 2 on the origin: closed to the app, noted (with the origin's schema record) and renamed to its copy.
    A move cut after its rename (its copy noted and there) goes on from the copy; without the hub's database or such a
    copy, there is nothing to move."""
    name = hub.db_name
    origin_id = getattr(origin, "pk", None)
    try:
        with ops.connect_ops(cluster=origin) as conn:
            present = _present(conn, name, copy_name)
            if control_services.pending_copy(hub.id) is not None and copy_name in present:
                ours()
                _close(conn, copy_name, roles)
                return
            if name not in present:
                raise MoveFailed("move_database_missing", f"{name} is not on the origin")
            ours()
            _close(conn, name, roles)
            if copy_name in present:
                # An older copy of this hub, from an earlier move off this server: the newer one replaces it.
                conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(_identifier(copy_name)))
                control_services.forget_copy(origin_id, copy_name)
            control_services.copy_pending(
                hub.id, origin_id, copy_name, schema_state=hub.schema_state, schema_apps=hub.schema_apps
            )
            ours()
            _rename(conn, name, copy_name)
    except psycopg.Error as error:
        raise MoveFailed("move_close_failed", ops.reason(error)) from error
    except ops.DatabaseOpsError as error:
        raise MoveFailed("move_close_failed", error) from error


def _dump(source: str, cluster, path: Path, heartbeat: Callable[[], None], cancelled=None) -> None:
    """Step 3, on the origin: ``pg_dump`` of ``source`` as the migrator (``base.tenancy.dumps``' own run)."""
    copied = SimpleNamespace(db_name=source, cluster=cluster, slug=source)
    try:
        dumps.run_pg_dump(
            copied, path, timeout=dumps.DUMP_TIMEOUT_SECONDS, heartbeat=heartbeat, cancelled=cancelled
        )
    except dumps.DumpError as failed:
        raise MoveFailed("move_dump_failed", failed) from failed


def _make_destination(hub, target, roles: bootstrap.Names, ours=None) -> None:
    """Step 3, on the destination: its database cloned from the template of its vertical there, the template's tables
    taken out. A database of that name there is never the hub's live one by now (the data is in the copy): a leftover
    of a move cut short, dropped first, unless control says it is a hub's database on that cluster (``MoveStopped``)."""
    try:
        template = provision.template_for(hub)
    except services.ProvisioningFailed as missing:
        raise MoveFailed("move_template_missing", missing) from missing
    if control_services.attributed(target.pk, hub.db_name, besides=hub.id):
        raise MoveStopped(f"control says {hub.db_name} on {target.name} is a hub's database: it is never dropped.")
    if ours is not None:
        ours()
    try:
        ops.drop_database(hub.db_name, cluster=target)
        ops.clone_database(hub.db_name, template=template, cluster=target, roles=roles)
    except ops.TemplateMissing as missing:
        raise MoveFailed("move_template_missing", missing) from missing
    except ops.DatabaseOpsError as refused:
        raise MoveFailed("move_clone_failed", refused) from refused
    try:
        with ops.connect_ops(hub.db_name, cluster=target) as conn, conn.transaction():
            _empty(conn)
    except (psycopg.Error, ops.DatabaseOpsError) as error:
        raise MoveFailed("move_clone_failed", f"its template's tables could not be taken out: {error}") from error


#: What the template's clone has that the restore makes again: tables, views and foreign tables of ``public`` that no
#: extension owns (the sequences of a table go with it).
_RELATIONS = {"r": "TABLE", "p": "TABLE", "v": "VIEW", "m": "MATERIALIZED VIEW", "f": "FOREIGN TABLE"}


def _empty(conn) -> None:
    rows = conn.execute(
        "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = ANY(%s) AND NOT c.relispartition AND NOT EXISTS ("
        "SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')",
        [list(_RELATIONS)],
    ).fetchall()
    for relation, kind in rows:
        conn.execute(
            sql.SQL("DROP {} IF EXISTS {} CASCADE").format(
                sql.SQL(_RELATIONS[kind]), sql.Identifier("public", relation)
            )
        )


def pg_restore() -> str:
    """The ``pg_restore`` of the image (``postgresql-client-18``)."""
    import shutil

    found = shutil.which("pg_restore")
    if found is None:
        raise MoveFailed("move_restore_failed", "pg_restore is not installed on this machine.")
    return found


def _restore(path: Path, name: str, cluster, heartbeat: Callable[[], None], cancelled=None) -> None:
    """Step 3, on the destination: ``pg_restore`` of the dump into ``name``, in one transaction, as the migrator, its
    extensions and its public schema left out (:data:`SKIPPED_ENTRIES`)."""
    tool = pg_restore()
    try:
        listing = subprocess.run([tool, "--list", str(path)], check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as failed:
        raise MoveFailed("move_restore_failed", f"its copy could not be read: {failed.stderr.strip()}") from failed
    kept = _kept_entries(listing)
    entries = path.with_suffix(".list")
    entries.write_text("\n".join(kept) + "\n", encoding="utf-8")
    conninfo = tenancy_connections.migrator_conninfo(name, cluster=cluster)
    password = str(conninfo.pop("password", "") or "")
    dsn = make_conninfo(**{key: str(value) for key, value in conninfo.items() if value not in (None, "")})
    command = [
        tool,
        "--no-owner",
        "--no-acl",
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--single-transaction",
        f"--use-list={entries}",
        f"--dbname={dsn}",
        str(path),
    ]
    _run(command, password, path.with_suffix(".restore.err"), heartbeat, cancelled, what=f"the restore of {name}")


def _kept_entries(listing: str) -> list[str]:
    """The lines of ``pg_restore --list`` the restore keeps: all but :data:`SKIPPED_ENTRIES`."""
    return [line for line in listing.splitlines() if not any(entry in f"{line} " for entry in SKIPPED_ENTRIES)]


def _run(command: list[str], password: str, errors_path: Path, heartbeat, cancelled, *, what: str) -> None:
    """Run ``command`` with ``password`` in its environment only, within :data:`RESTORE_TIMEOUT_SECONDS`, its
    heartbeat every ``dumps.POLL_SECONDS``; a stop kills it."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env["PGPASSWORD"] = password
    env["PGGSSENCMODE"] = "disable"
    with open(errors_path, "w+", encoding="utf-8", errors="replace") as complaints:
        process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=complaints)
        started = last_beat = time.monotonic()
        try:
            while True:
                if cancelled is not None and cancelled():
                    raise MoveStopped(f"{what} was stopped: the worker is stopping.")
                left = RESTORE_TIMEOUT_SECONDS - (time.monotonic() - started)
                if left <= 0:
                    raise MoveFailed("move_restore_failed", f"{what} took longer than {RESTORE_TIMEOUT_SECONDS:g} s")
                try:
                    process.wait(timeout=min(dumps.POLL_SECONDS, dumps.STOP_CHECK_SECONDS, left))
                    break
                except subprocess.TimeoutExpired:
                    if time.monotonic() - last_beat >= dumps.POLL_SECONDS:
                        heartbeat()
                        last_beat = time.monotonic()
        except BaseException:
            process.kill()
            process.wait()
            raise
        if process.returncode != 0:
            complaints.seek(0)
            said = " ".join(line.strip() for line in complaints.read().splitlines()[-ERROR_LINES:] if line.strip())
            if password:
                said = said.replace(password, "***")
            raise MoveFailed("move_restore_failed", f"{what} failed (exit {process.returncode}): {said}")


def _verify_identity(name: str, cluster, hub_id) -> None:
    """Step 4: the moved database says it is this hub (``base_hub_identity``), and nobody else."""
    try:
        with ops.connect_ops(name, cluster=cluster) as conn:
            found = [row[0] for row in conn.execute("SELECT hub_id FROM base_hub_identity")]
    except (psycopg.Error, ops.DatabaseOpsError) as error:
        raise MoveFailed("move_identity_mismatch", f"its identity could not be read: {error}") from error
    if found != [hub_id]:
        raise MoveFailed("move_identity_mismatch", f"it says it is {[str(value) for value in found]}, not {hub_id}")


def _ensure_schema(hub, target, heartbeat=None) -> None:
    """Step 4: the moved database brought to the code's leaf on its new cluster, the lease renewed meanwhile."""
    moved = copying.copy(hub)
    moved.cluster = target
    try:
        migrator.ensure_schema(moved, heartbeat=heartbeat)
    except Exception as error:
        raise MoveFailed("move_schema_failed", f"{type(error).__name__}: {error}") from error


def _switch(hub_id, target, origin, copy_name: str, now: dt.datetime) -> None:
    """Step 5: control moves the hub and dates its copy, in one transaction on its locked row, only if the move is
    still this worker's (``MoveStopped`` otherwise: nothing written)."""
    try:
        control_services.move_finished(
            hub_id, target.pk, getattr(origin, "pk", None), copy_name, now, owner=services.LEASE_OWNER
        )
    except control_services.MoveTaken as taken:
        raise MoveStopped(str(taken)) from taken


def _undo(hub, copy_name: str, origin, target, roles: bootstrap.Names, ours, now: dt.datetime) -> bool:
    """Back where it was, the origin first; whether a copy of that name stayed on the origin (an older one: the hub's
    data never left). Only the worker's note says the data is in the copy: then what has the hub's name on the
    destination is dropped if it answers (noted as left over if not), and the copy is renamed back, but only where the
    hub's database is not (one that is there never left). The origin is opened to the app again when its database is
    there."""
    ours(forward=False)
    noted = control_services.pending_copy(hub.id) is not None
    with ops.connect_ops(cluster=origin) as conn:
        present = _present(conn, hub.db_name, copy_name)
    if noted and copy_name in present:
        if not _drop_destination(hub, target, origin=origin, copy_name=copy_name):
            control_services.leftover_noted(hub.id, target.pk, hub.db_name, now)
        with ops.connect_ops(cluster=origin) as conn:
            present = _present(conn, hub.db_name, copy_name)
    copy_kept = False
    if noted and copy_name in present:
        if hub.db_name in present:
            copy_kept = True
        else:
            ours(forward=False)
            _rename_back(origin, copy_name, hub.db_name)
    with ops.connect_ops(cluster=origin) as conn:
        if hub.db_name in _present(conn, hub.db_name):
            _open(conn, hub.db_name, roles)
    return copy_kept


def _drop_destination(hub, target, *, origin=None, copy_name: str = "") -> bool:
    """Drop what the move made of ``hub``'s database on ``target`` (never one control says is a hub's there, nor, on the
    origin's own server, while the copy that holds the data is not there); whether it is gone (``False``: the
    destination did not answer)."""
    if control_services.attributed(target.pk, hub.db_name, besides=hub.id):
        raise MoveStopped(f"control says {hub.db_name} on {target.name} is a hub's database: it is never dropped.")
    try:
        if _same_server(origin, target):
            with ops.connect_ops(cluster=target) as conn:
                if copy_name not in _present(conn, copy_name):
                    raise MoveStopped(f"{hub.db_name} on {target.name} is the origin's server and its copy is not there.")
        ops.drop_database(hub.db_name, cluster=target)
    except ops.DatabaseOpsError as unreachable:
        logger.warning("base.tenancy.move.destination_unreachable hub=%s: %s; noted to drop later.", hub.slug, unreachable)
        return False
    return True


def _rename_back(origin, copy_name: str, name: str) -> None:
    with ops.connect_ops(cluster=origin) as conn:
        _rename(conn, copy_name, name)


def _drop_copy(name: str, cluster) -> None:
    """Drop the copy ``name`` on ``cluster`` (none: the settings' own server); only a moved copy's name passes."""
    target = sql.Identifier(names.validate_moved(name, control=tenancy_connections.control_name()))
    with ops.connect_ops(cluster=cluster) as conn:
        try:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(target))
        except psycopg.Error as error:
            raise ops.DatabaseOpsError(f"{name!r} could not be dropped: {ops.reason(error)}") from error


def _close_this_processs(hub) -> None:
    """This thread's connections to the hub's database (its alias and its migrator's), closed: wherever they reached."""
    tenancy_connections.close_hub_aliases(hub)
