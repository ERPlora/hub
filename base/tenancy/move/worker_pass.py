"""The moves' pass of the worker: the moves asked for a night that came started, one hub moved, then the copies
past their days and what undone moves left on their destinations dropped."""

import datetime as dt
import logging
from collections.abc import Callable

from django.utils import timezone

from base import services
from base.tenancy import bootstrap, ops
from base.tenancy.move import databases, moving
from control import services as control_services

logger = logging.getLogger("base.tenancy.move")  # one logger for every part of the move

#: How long the copy a hub leaves behind is kept before it is dropped.
MOVED_COPY_DAYS = 7


def run_due(
    now: dt.datetime | None = None,
    *,
    roles: bootstrap.Names | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> int:
    """The worker's pass: start the moves asked for a night that came (:func:`launch_due`), move the hub asked longest
    ago whose lease nobody else holds (one a pass: a copy takes a while), then drop the copies past their days; how many
    hubs it worked on. ``roles``: the app's roles the origin is closed to (default the environment's); ``cancelled``:
    whether the worker is stopping."""
    now = now or timezone.now()
    launch_due(now)
    worked = 0
    for hub_id in control_services.hubs_moving():
        if services.provisioning.claim_hub(hub_id, now, moving.LEASE) is None:
            continue
        try:
            moving.move_hub(hub_id, now=now, roles=roles, cancelled=cancelled)
            worked = 1
        finally:
            services.provisioning.release_hub(hub_id, timezone.now())
        break
    drop_old_copies(now)
    drop_leftovers(now)
    return worked


def launch_due(now: dt.datetime) -> int:
    """Start each move asked for a night that is due by ``now`` whose hub's lease nobody else holds
    (``control.services.start_scheduled_move``): one whose night has not come on the business's clock waits for it, one
    refused says why; a failure of one is logged and it is tried again on the next pass. How many started."""
    started = 0
    for hub_id in control_services.moves_scheduled_due(now):
        if services.provisioning.claim_hub(hub_id, now, moving.LEASE) is None:
            continue
        try:
            if control_services.start_scheduled_move(hub_id, now, owner=services.provisioning.LEASE_OWNER):
                started += 1
                logger.info("move: the move of %s asked for its night started.", hub_id)
        except Exception:
            logger.exception("move: the move of %s asked for its night could not start; the next pass retries.", hub_id)
        finally:
            services.provisioning.release_hub(hub_id, timezone.now())
    return started


def drop_old_copies(now: dt.datetime) -> int:
    """Drop the copies left behind more than :data:`MOVED_COPY_DAYS` before ``now``, with their rows; how many. One that
    cannot be dropped now stays, and the next pass tries again."""
    dropped = 0
    for kept in control_services.copies_due(now - dt.timedelta(days=MOVED_COPY_DAYS)):
        try:
            databases._drop_copy(kept.db_name, kept.cluster)
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
        if services.provisioning.claim_hub(left.hub_id, timezone.now(), moving.LEASE) is None:
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
            services.provisioning.release_hub(left.hub_id, timezone.now())
    return dropped


def _leftover_droppable(hub, left) -> bool:
    return not (
        control_services.attributed(left.cluster_id, left.db_name) or databases._same_server(hub.cluster, left.cluster)
    )
