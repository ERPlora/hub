"""Steps 1 and 2, on the origin: the hub's database closed to the app, its copy noted in control and renamed."""

import psycopg
from psycopg import sql

from base.tenancy import bootstrap, ops
from base.tenancy.move import databases
from base.tenancy.move.exceptions import MoveFailed
from control import services as control_services


def _close_and_rename(hub, copy_name: str, origin, roles: bootstrap.Names, ours) -> None:
    """Steps 1 and 2 on the origin: closed to the app, noted (with the origin's schema record) and renamed to its copy.
    A move cut after its rename (its copy noted and there) goes on from the copy; without the hub's database or such a
    copy, there is nothing to move."""
    name = hub.db_name
    origin_id = getattr(origin, "pk", None)
    try:
        with ops.connect_ops(cluster=origin) as conn:
            present = databases._present(conn, name, copy_name)
            if control_services.pending_copy(hub.id) is not None and copy_name in present:
                ours()
                databases._close(conn, copy_name, roles)
                return
            if name not in present:
                raise MoveFailed("move_database_missing", f"{name} is not on the origin")
            ours()
            databases._close(conn, name, roles)
            if copy_name in present:
                # An older copy of this hub, from an earlier move off this server: the newer one replaces it.
                conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(databases._identifier(copy_name)))
                control_services.forget_copy(origin_id, copy_name)
            control_services.copy_pending(
                hub.id, origin_id, copy_name, schema_state=hub.schema_state, schema_apps=hub.schema_apps
            )
            ours()
            databases._rename(conn, name, copy_name)
    except psycopg.Error as error:
        raise MoveFailed("move_close_failed", ops.reason(error)) from error
    except ops.DatabaseOpsError as error:
        raise MoveFailed("move_close_failed", error) from error
