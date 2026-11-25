"""One hub's move, its steps in their order under the hub's lease, and its undoing when one of them fails."""

import datetime as dt
import logging
from collections.abc import Callable

from django.utils import timezone

from base import services
from base.tenancy import bootstrap, dumps, names, ops, provision
from base.tenancy import connections as tenancy_connections
from base.tenancy.move import bucket, closing, destination, undo
from base.tenancy.move.exceptions import MoveFailed, MoveStopped
from control import services as control_services

logger = logging.getLogger("base.tenancy.move")  # one logger for every part of the move

#: The worker's lease of a moving hub: provisioning's, renewed while it copies.
LEASE = provision.LEASE
#: The kind of a move's copy in the dumps bucket (``<hex>/<AAAAMMDDTHHMMSSZ>-move.dump``).
MOVE_DUMP_KIND = "move"
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
        services.reset.renew_lease(hub.id, LEASE)

    def ours(*, forward: bool = True) -> None:
        heartbeat()
        try:
            control_services.still_ours(hub.id, target.pk, services.provisioning.LEASE_OWNER, forward=forward)
        except control_services.MoveTaken as taken:
            raise MoveStopped(str(taken)) from taken

    back = {"hub": hub, "copy_name": copy_name, "origin": origin, "target": target, "roles": roles, "now": now}
    try:
        if hub.move_undo_asked_at is not None:
            reason = hub.last_error.split(UNDO_FAILED_MARK)[0] or "move_cancelled: the move was asked to be undone"
            _back(**back, ours=ours, reason=reason)
            return
        try:
            bucket._bucket_named()
            closing._close_and_rename(hub, copy_name, origin, roles, ours)
            # Their heartbeat checks the move is still this worker's: a cancel or a lease lost stops them.
            key = dumps.key_for(hub, MOVE_DUMP_KIND, timezone.now())
            bucket._dump_to_bucket(key, copy_name, origin, ours, cancelled)
            destination._make_destination(hub, target, roles, ours)
            bucket._restore_from_bucket(key, hub.db_name, target, ours, cancelled)
            heartbeat()
            destination._verify_identity(hub.db_name, target, hub.id)
            destination._ensure_schema(hub, target, heartbeat)
            _switch(hub.id, target, origin, copy_name, now)
        except (services.provisioning.ProvisioningStopped, MoveStopped, dumps.DumpStopped) as stopped:
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


def _back(hub, copy_name: str, origin, target, roles, now, ours, *, reason: str) -> None:  # noqa: PLR0913, PLR0917
    """Undo the move of ``hub`` and note why; one that cannot be undone now stays moving, to be undone next time."""
    try:
        undo._undo(hub, copy_name, origin, target, roles, ours, now)
    except (services.provisioning.ProvisioningStopped, MoveStopped) as stopped:
        logger.info("base.tenancy.move.stopped hub=%s: %s; left to whoever holds it now.", hub.slug, stopped)
        return
    except Exception as undo_error:
        logger.exception("base.tenancy.move.undo_failed hub=%s: it stays moving and is undone next time.", hub.slug)
        control_services.move_stuck(hub.id, f"{reason}{UNDO_FAILED_MARK}{type(undo_error).__name__}: {undo_error})")
        return
    control_services.move_undone(hub.id, getattr(origin, "pk", None), copy_name, reason)
    logger.info("base.tenancy.move.undone hub=%s: %s", hub.slug, reason)


def _switch(hub_id, target, origin, copy_name: str, now: dt.datetime) -> None:
    """Step 5: control moves the hub and dates its copy, in one transaction on its locked row, only if the move is
    still this worker's (``MoveStopped`` otherwise: nothing written)."""
    try:
        control_services.move_finished(
            hub_id, target.pk, getattr(origin, "pk", None), copy_name, now, owner=services.provisioning.LEASE_OWNER
        )
    except control_services.MoveTaken as taken:
        raise MoveStopped(str(taken)) from taken


def _close_this_processs(hub) -> None:
    """This thread's connections to the hub's database (its alias and its migrator's), closed: wherever they reached."""
    tenancy_connections.close_hub_aliases(hub)
