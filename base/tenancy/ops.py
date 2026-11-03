"""The migrator's maintenance connection: a hub's database made and dropped (PLAN-DB §6; round 2026-10-30, S2a).

``CREATE DATABASE`` and ``DROP DATABASE`` cannot run in a transaction, nor through PgBouncer in transaction mode, nor
on a Django alias (whose transactions the tests and ``@operation`` wrap): :func:`connect_ops` opens a direct ``psycopg``
connection to the maintenance database ``postgres``, as the migrator's role (``DB_MIGRATOR_USER``, which the worker
and ``hub-migrate`` have and the web does not; the default connection's role where it is not set), in autocommit,
and closes it on the way out.

- :func:`clone_database` makes a hub's or a demo's database as a copy of its template (``CREATE DATABASE … TEMPLATE``;
  its owner is the migrator that connects), on the hub's cluster: a template only clones within its cluster, so it is
  that cluster's ``<control>_template[_<vertical>]`` (:class:`TemplateMissing` when it has none). A database that is
  already there (``42P04``) is no failure: the second call of a provisioning that was cut short goes on from there. A
  template someone is connected to (``55006``) is waited for a bounded while (:data:`TEMPLATE_BUSY_WAITS`), then a
  readable failure. Every call then makes the database private: nothing to ``PUBLIC``, ``CONNECT`` and ``TEMPORARY`` to
  the environment's ``hub_app`` and ``hub_admin`` (``bootstrap.Names``, with pre's ``pre_`` prefix); a role the server
  does not have (local development, the tests) is skipped and logged.
- :func:`drop_database` drops one hub's or demo's database, the sessions on it included (``WITH (FORCE)``); a
  template or any other name is refused before the server hears it.

Every name is validated by ``base.tenancy.names`` and reaches SQL as ``sql.Identifier``, never by formatting a string.
Every server refusal is a :class:`DatabaseOpsError` with the server's own message, never the statement.
"""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

import psycopg
from psycopg import errors, sql

from base.tenancy import bootstrap, names
from base.tenancy import connections as tenancy_connections

logger = logging.getLogger(__name__)

#: Where ``CREATE``/``DROP DATABASE`` run: a database of the server that is nobody's.
MAINTENANCE_DATABASE = "postgres"
#: The waits between the attempts to clone a template someone is connected to. The server itself waits up to 5 s for
#: them to leave before it refuses (``55006``), so three attempts take about 17 s at most.
TEMPLATE_BUSY_WAITS = (0.5, 1.0)


class DatabaseOpsError(RuntimeError):
    """What the server refused to a clone or a drop: its own message and the database's name, never the statement."""


class TemplateMissing(DatabaseOpsError):
    """The template a hub is cloned from is not on its cluster (``migrate_hubs`` makes them on every open one)."""


def reason(error: psycopg.Error) -> str:
    diag = getattr(error, "diag", None)
    return (diag and diag.message_primary) or str(error).strip()


@contextmanager
def connect_ops(database: str = MAINTENANCE_DATABASE, *, cluster=None) -> Iterator[psycopg.Connection]:
    """The migrator's direct connection to ``database`` (``postgres`` by default) on ``cluster`` (or the settings'
    own server), in autocommit; closed after."""
    try:
        conn = psycopg.connect(**tenancy_connections.migrator_conninfo(database, cluster=cluster), autocommit=True)
    except psycopg.Error as error:
        raise DatabaseOpsError(f"The migrator cannot connect to {database!r}: {reason(error)}") from error
    try:
        yield conn
    finally:
        conn.close()


def environment_roles(control: str) -> bootstrap.Names:
    """The roles of the environment whose control database is ``control``: prod's for ``hub``, pre's for ``pre_hub``."""
    production = bootstrap.Names().control
    prefix = control[: -len(production)] if control.endswith(production) else ""
    try:
        return bootstrap.Names.with_prefix(prefix)
    except ValueError:
        return bootstrap.Names()


def clone_database(
    name: str,
    *,
    template: str,
    cluster=None,
    roles: bootstrap.Names | None = None,
    waits: Sequence[float] = TEMPLATE_BUSY_WAITS,
    sleep: Callable[[float], object] = time.sleep,
) -> bool:
    """Make ``name`` a clone of ``template`` on ``cluster`` (or the settings' own server) and private to the
    environment's roles; whether this call made it.

    ``False`` when it was there already (its privileges are set again all the same). ``DatabaseOpsError`` when the
    template stayed in use through ``waits`` or the server refused it (a missing template, no ``CREATEDB``).
    """
    control = tenancy_connections.control_name()
    target = sql.Identifier(names.validate_hub(name, control=control))
    source = names.identifier(template, control=control)
    roles = environment_roles(control) if roles is None else roles
    with connect_ops(cluster=cluster) as conn:
        statement = sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(target, source)
        made = _create(conn, statement, name, template, waits, sleep)
        _make_private(conn, target, name, roles)
    return made


def _create(conn, statement, name: str, template: str, waits: Sequence[float], sleep) -> bool:
    for wait in (*waits, None):
        try:
            conn.execute(statement)
        except errors.DuplicateDatabase:
            return False
        except errors.ObjectInUse as busy:
            if wait is None:
                raise DatabaseOpsError(
                    f"The template {template!r} is in use: {name!r} could not be cloned from it ({reason(busy)})."
                ) from busy
            sleep(wait)
            continue
        except errors.InvalidCatalogName as missing:
            raise TemplateMissing(
                f"The template {template!r} is not on this cluster: {name!r} could not be cloned ({reason(missing)})."
            ) from missing
        except psycopg.Error as error:
            raise DatabaseOpsError(f"{name!r} could not be cloned from {template!r}: {reason(error)}") from error
        return True
    raise AssertionError("unreachable: the last attempt returns or raises")


def _make_private(conn, target: sql.Identifier, name: str, roles: bootstrap.Names) -> None:
    wanted = [roles.hub_app, roles.hub_admin]
    try:
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(target))
        present = {row[0] for row in conn.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", [wanted])}
        granted = [role for role in wanted if role in present]
        if granted:
            conn.execute(
                sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                    target, sql.SQL(", ").join(map(sql.Identifier, granted))
                )
            )
    except psycopg.Error as error:
        raise DatabaseOpsError(f"The privileges of {name!r} could not be set: {reason(error)}") from error
    for role in wanted:
        if role not in present:
            logger.warning(
                "base.tenancy.ops.role_missing role=%s database=%s: no such role on the server; nothing granted.",
                role,
                name,
            )


def drop_database(name: str, *, cluster=None) -> bool:
    """Drop the hub's or demo's database ``name`` on ``cluster`` (or the settings' own server), whoever is connected
    to it; whether it was there."""
    target = sql.Identifier(names.validate_hub(name, control=tenancy_connections.control_name()))
    with connect_ops(cluster=cluster) as conn:
        try:
            existed = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone() is not None
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(target))
        except psycopg.Error as error:
            raise DatabaseOpsError(f"{name!r} could not be dropped: {reason(error)}") from error
    return existed
