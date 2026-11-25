"""Steps 3 and 4 on the destination: its database cloned from its template there and emptied of its tables, then
checked to be the hub's and brought to the code's leaf."""

import copy as copying

import psycopg
from psycopg import sql

from base import services
from base.tenancy import bootstrap, migrator, ops, provision
from base.tenancy.move import databases
from base.tenancy.move.exceptions import MoveFailed, MoveStopped
from control import services as control_services


def _make_destination(hub, target, roles: bootstrap.Names, ours=None) -> None:
    """Step 3, on the destination: its database cloned from the template of its vertical there, the template's tables
    taken out. A database of that name there is never the hub's live one by now (the data is in the copy): a leftover
    of a move cut short, dropped first, unless control says it is a hub's database on that cluster (``MoveStopped``)."""
    try:
        template = provision.template_for(hub)
    except services.provisioning.ProvisioningFailed as missing:
        raise MoveFailed("move_template_missing", missing) from missing
    if control_services.worker_move.attributed(target.pk, hub.db_name, besides=hub.id):
        raise MoveStopped(f"control says {hub.db_name} on {target.name} is a hub's database: it is never dropped.")
    if ours is not None:
        ours()
    _clone_emptied(hub, target, roles, template)


def _clone_emptied(hub, cluster, roles: bootstrap.Names, template: str | None = None, *, aside: str = "") -> None:
    """``hub``'s database on ``cluster`` made anew: whatever has its name there dropped, cloned from the template of its
    vertical there (``template``, found when not given) and the template's tables taken out. The caller makes sure
    what has that name is never the hub's data. ``aside``: a separate copy of the hub of that name made instead
    (``base.tenancy.restore``), granted to none of the app's roles."""
    if template is None:
        try:
            template = provision.template_for(hub)
        except services.provisioning.ProvisioningFailed as missing:
            raise MoveFailed("move_template_missing", missing) from missing
    name = aside or hub.db_name
    try:
        if aside:
            databases._drop_copy(aside, cluster)
        else:
            ops.drop_database(hub.db_name, cluster=cluster)
        ops.clone_database(name, template=template, cluster=cluster, roles=roles, aside=bool(aside))
    except ops.TemplateMissing as missing:
        raise MoveFailed("move_template_missing", missing) from missing
    except ops.DatabaseOpsError as refused:
        raise MoveFailed("move_clone_failed", refused) from refused
    try:
        with ops.connect_ops(name, cluster=cluster) as conn, conn.transaction():
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
        migrator.schema.ensure_schema(moved, heartbeat=heartbeat)
    except Exception as error:
        raise MoveFailed("move_schema_failed", f"{type(error).__name__}: {error}") from error
