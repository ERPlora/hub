"""What a move runs on the databases of a server: which server a cluster is, which databases it has, closing one to
the app and opening it again, renaming one and dropping a copy left behind."""

import socket
import time

import psycopg
from django.conf import settings
from psycopg import errors, sql

from base.tenancy import bootstrap, names, ops
from base.tenancy import connections as tenancy_connections
from base.tenancy.move.exceptions import MoveFailed


#: How many times the rename waits for a session that came back to the origin before it gives up.
RENAME_WAITS = (0.5, 1.0)


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


def _drop_copy(name: str, cluster) -> None:
    """Drop the copy ``name`` on ``cluster`` (none: the settings' own server); only the name of a copy a hub left
    behind passes (moved, or kept by a restore)."""
    target = sql.Identifier(names.validate_left_behind(name, control=tenancy_connections.control_name()))
    with ops.connect_ops(cluster=cluster) as conn:
        try:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(target))
        except psycopg.Error as error:
            raise ops.DatabaseOpsError(f"{name!r} could not be dropped: {ops.reason(error)}") from error
