"""The worker's slow passes over the data, each in a thread of its own (``base.worker.Background``): a hub's data
work, the nightly measurement and the moves."""

import datetime as dt
import logging
import threading
from collections.abc import Callable

from django.db import close_old_connections
from django.utils import timezone

from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base import schemas, services, usage
from base.tenancy import dumps, move, offboarding, provision, recovery, restore
from base.tenancy.connections import close_hub_aliases
from base.tenancy.context import use_control, use_hub
from control.models.dumps import HubDump
from control.models.hubs import Hub

logger = logging.getLogger("base.worker")  # logged as the worker, whose passes these are

#: The last night this process measured (``base.usage``): the next tick checks the registry again only for a newer one.
_measured: dt.date | None = None
#: How long the lease of a hub whose sections are being emptied lasts (its copy renews a lease of a minute while it
#: runs; the emptying is one transaction of the hub's that does not renew it).
EMPTYING_LEASE = dt.timedelta(minutes=15)


def _data(now: dt.datetime, stop: threading.Event | None = None) -> bool:
    """The data work of one hub due by ``now``, under its lease: a reset asked (its database copied, then its sections
    emptied), the copy of a business that left, or a business past its 90 days (``base.tenancy.offboarding``). It runs in
    the worker's data thread (:class:`Background`), one hub at a time: a copy takes a while, and the loop goes on
    meanwhile. A failure is logged and the work stays due (a lease lost is left to its holder); ``stop`` set stops the
    copy in course, its lease given back. Whether it took a hub or failed to read them: the next tick looks again."""
    try:
        with use_control():
            hub_id = services.offboarding.claim_next_data_hub(now, provision.LEASE)
    except Exception:
        logger.exception("worker: the hubs with data work could not be read; the next tick tries again.")
        close_old_connections()
        return True
    if hub_id is None:
        return False
    try:
        with use_control():
            hub = services.provisioning.registry_row(hub_id)
            cancelled = stop.is_set if stop is not None else None
            if hub is not None and hub.reset_requested_at is not None:
                _reset(hub, cancelled)
            elif hub is not None and services.offboarding.past_retention(hub, now):
                offboarding.retire(hub.pk, now, cancelled)
            elif hub is not None and services.provisioning.offboarding_due(hub):
                _offboarding_copy(hub, now, cancelled)
    except dumps.DumpStopped:
        logger.info("worker: the copy of the hub %s was stopped with the worker; it stays due.", hub_id)
    except Exception:
        logger.exception("worker: the data work of the hub %s failed; it is tried again.", hub_id)
    finally:
        try:
            with use_control():
                services.provisioning.release_hub(hub_id, timezone.now())
        except Exception:
            logger.exception("worker: the lease of the hub %s could not be given back; it runs out by itself.", hub_id)
        row = services.provisioning.registry_row(hub_id) if hub_id else None
        if row is not None and row.db_name:
            close_hub_aliases(row)
        close_old_connections()
    return True


def _usage(now: dt.datetime) -> None:
    """Measure the last UTC day that ended (``base.usage``: 00:15, once a night, whichever worker claims it); a failure
    is logged and the next tick tries again."""
    global _measured
    day = usage.day_due(now)
    if _measured is not None and _measured >= day:
        return
    try:
        with use_control():
            measured = None if services.usage.usage_ready(day) else usage.measure(day, now=now)
            finished = measured is not None or services.usage.usage_ready(day)
    except Exception:
        logger.exception("worker: the nightly measurement failed (%s); the next tick tries again.", day)
        return
    finally:
        close_old_connections()
    # Another worker measuring it: this one looks again next tick, and takes it over if that one stopped.
    if finished:
        _measured = day
    if measured is not None:
        logger.info("worker: measured the use of %d hub(s) on %s.", measured, day)


def _moves(now: dt.datetime, stop: threading.Event | None = None) -> bool:
    """Move the hub asked longest ago to its new cluster and drop the copies past their days
    (``base.tenancy.move.worker_pass.run_due``), then restore the hub asked longest ago from its copy
    (``base.tenancy.restore.run_due``),
    make the separate copy asked longest ago (``base.tenancy.restore.run_aside_due``) and bring back into its business
    what a made copy was asked to give back (``base.tenancy.recovery.run_due``), on control, in the worker's move thread
    (:class:`Background`); a failure is logged and the next pass tries again. ``stop`` set stops the copy in course and
    leaves it for the next worker to go on. Whether it worked on one, or failed: the next tick starts it again."""
    cancelled = stop.is_set if stop is not None else None
    try:
        with use_control():
            moved = move.worker_pass.run_due(now, cancelled=cancelled)
            moved += restore.run_due(now, cancelled=cancelled)
            moved += restore.run_aside_due(now, cancelled=cancelled)
            moved += recovery.run_due(now, cancelled=cancelled)
    except Exception:
        logger.exception("worker: the moves' pass failed; the next tick tries again.")
        return True
    finally:
        close_old_connections()
    if moved:
        logger.info("worker: worked on the move, the restore, a separate copy or a recovery of %d hub(s).", moved)
    return bool(moved)


def _heartbeat(hub) -> Callable[[], None]:
    return lambda: services.reset.renew_lease(hub.pk, provision.LEASE)


def _reset(hub, cancelled: Callable[[], bool] | None = None) -> None:
    """Copy the database of ``hub`` and, only if the copy was kept, empty the sections asked; each step noted."""
    asked = hub.reset_sections or {}
    if hub.status != Hub.Status.READY or not hub.db_name:
        services.reset.reset_moved(hub.pk, state="failed", error="hub_not_ready")
        logger.warning("worker: the reset of %s was not done: the business is %s.", hub.slug, hub.status)
        return
    try:
        copy = dumps.dump_hub(
            hub,
            kind=HubDump.Kind.RESET,
            requested_by=asked.get("requested_by", ""),
            heartbeat=_heartbeat(hub),
            cancelled=cancelled,
        )
    except dumps.DumpError as failed:
        logger.warning("worker: the copy before the reset of %s failed, nothing was emptied: %s", hub.slug, failed)
        services.reset.reset_moved(hub.pk, state="failed", error=failed.code)
        return
    services.reset.reset_moved(hub.pk, state="emptying", dump=str(copy.pk))
    services.reset.renew_lease(hub.pk, EMPTYING_LEASE)
    ctx = OperationContext(
        scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language=asked.get("language") or "en"
    )
    try:
        with use_hub(hub):
            done = get_operation("base.hub.reset_apply")(ctx, schemas.reset.HubResetApplyIn(apps=asked.get("apps") or []))
    except Exception:
        logger.exception("worker: the sections of %s could not be emptied; its copy is kept, nothing was emptied.", hub.slug)
        services.reset.reset_moved(hub.pk, state="failed", error="emptying_failed")
        return
    services.reset.reset_moved(hub.pk, state="done", removed=[app.model_dump(mode="json") for app in done.apps])
    logger.info("worker: the business %s was reset (%s) after its copy %s.", hub.slug, ", ".join(asked.get("apps") or []), copy.key)


def _offboarding_copy(hub, now: dt.datetime, cancelled: Callable[[], bool] | None = None) -> None:
    """Copy the database of the business ``hub`` that left; a failure is tried again at its next attempt."""
    try:
        dumps.dump_hub(hub, kind=HubDump.Kind.OFFBOARDING, heartbeat=_heartbeat(hub), cancelled=cancelled)
    except dumps.DumpError as failed:
        logger.warning("worker: the copy of %s, which left, failed; it is tried again: %s", hub.slug, failed)
        services.offboarding.offboarding_copy_failed(hub.pk, now, f"{failed.code}: {failed}")
        return
    services.offboarding.offboarding_copied(hub.pk)
