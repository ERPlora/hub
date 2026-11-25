"""A move undone: the hub back on its origin, the destination dropped (or noted to drop later) and the copy renamed
back."""

import datetime as dt
import logging

from base.tenancy import bootstrap, ops
from base.tenancy.move import databases
from base.tenancy.move.exceptions import MoveFailed, MoveStopped
from control import services as control_services

logger = logging.getLogger("base.tenancy.move")  # one logger for every part of the move


def _undo(hub, copy_name: str, origin, target, roles: bootstrap.Names, ours, now: dt.datetime) -> None:  # noqa: PLR0913, PLR0917
    """Back where it was, the origin first. Only the worker's note says the data is in the copy (an older copy is dropped
    before the note is written, so a copy there with the note is this move's): then what has the hub's name on the
    destination is dropped if it answers (noted as left over if not) and the copy renamed back. A database with the
    hub's name still on the origin's server then is the destination's or a leftover, never the hub's data: the undo
    fails (``MoveFailed``) and is tried again, and no such database is ever opened to the app as the hub's. Without the
    note, the data never left: the origin is opened to the app again when its database is there."""
    ours(forward=False)
    noted = control_services.worker_move.pending_copy(hub.id) is not None
    with ops.connect_ops(cluster=origin) as conn:
        present = databases._present(conn, hub.db_name, copy_name)
    if noted and copy_name in present:
        if not _drop_destination(hub, target, origin=origin, copy_name=copy_name):
            control_services.worker_move.leftover_noted(hub.id, target.pk, hub.db_name, now)
        with ops.connect_ops(cluster=origin) as conn:
            if hub.db_name in databases._present(conn, hub.db_name):
                raise MoveFailed(
                    "move_undo_blocked",
                    f"{hub.db_name} on the origin's server is not the hub's data (that is in {copy_name}): it could not "
                    "be dropped yet",
                )
        ours(forward=False)
        _rename_back(origin, copy_name, hub.db_name)
    with ops.connect_ops(cluster=origin) as conn:
        if hub.db_name in databases._present(conn, hub.db_name):
            databases._open(conn, hub.db_name, roles)


def _drop_destination(hub, target, *, origin=None, copy_name: str = "") -> bool:
    """Drop what the move made of ``hub``'s database on ``target`` (never one control says is a hub's there, nor, on the
    origin's own server, while the copy that holds the data is not there); whether it is gone (``False``: the
    destination did not answer)."""
    if control_services.worker_move.attributed(target.pk, hub.db_name, besides=hub.id):
        raise MoveStopped(f"control says {hub.db_name} on {target.name} is a hub's database: it is never dropped.")
    try:
        if databases._same_server(origin, target):
            with ops.connect_ops(cluster=target) as conn:
                if copy_name not in databases._present(conn, copy_name):
                    raise MoveStopped(f"{hub.db_name} on {target.name} is the origin's server and its copy is not there.")
        ops.drop_database(hub.db_name, cluster=target)
    except ops.DatabaseOpsError as unreachable:
        logger.warning("base.tenancy.move.destination_unreachable hub=%s: %s; noted to drop later.", hub.slug, unreachable)
        return False
    return True


def _rename_back(origin, copy_name: str, name: str) -> None:
    with ops.connect_ops(cluster=origin) as conn:
        databases._rename(conn, copy_name, name)
