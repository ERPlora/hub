"""The Hub's worker (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

``manage.py run_worker`` runs it in the ``worker`` task, one per deploy. It first registers the
Hub's modules in the SaaS's registry (round 16, PLAN §21.1.1): without its apps registered there is
no release, so it does no work before that. Two cases (first production deploy, 2026-10-14):

- the SaaS has not migrated the ``shared`` schema yet (``SharedSchemaNotReady``: its tables do not
  exist): transient, so it warns and retries after 5, 10, 20, 40 and then every 60 s, running and
  without working, so ECS sees a stable task; a stop request during the wait exits 0;
- any other failure, a missing column included (a contract gap, spec §3.5): fatal, 1, and ECS's
  ``task_failed`` rule reports it.

Then it schedules the apps' tasks once (``scheduler.sync``: a failure is fatal, 1) and, every tick
(5 s), runs the ones that are due (``scheduler.run_due``): the VeriFactu queue every minute
(VERIFACTU-F20) and every other ``scheduled_tasks`` an app declares, each claimed with ``SKIP LOCKED``.
A tick that fails (the database went away) is logged and the next one tries again; a stop request
ends the loop at once. Every tick, after the tasks and whatever they did, it relays the outbox
(``base.relay``, round 2026-10-20 of PLAN-HUB): each new event to the reactions of the apps that listen
to it, exactly once, in the scope of the hub that recorded it; a pass that fails is logged and the next
tick tries again. What a reaction or a task leaves for after its COMMIT that waits on the network (a call to another
system) runs off this loop, in ``base.outbound``'s threads, so it never holds the next delivery nor the next task; on
its way out the worker gives what still runs ``OUTBOUND_GRACE_SECONDS`` and drops what waits (their lease sends them
again). On the first tick and then every ``REAPER_INTERVAL_SECONDS`` it also purges the
demo hubs that ended (``base.services.reap_demos``, plan 2026-10-17 §1.7), whatever the scheduler did: a
pass that fails is logged and the next one tries again, and the worker never stops for it. Every pass
releases its connection. Phase 1 runs the tasks on one fixed scope (``WORKER_SCOPE_SLUG``) and relays the
one database every hub shares; phase 2 adds, in this loop, the hubs whose ``hub_due`` has come (each under
``use_hub``, for its tasks and its outbox) and the hubs' provisioning and purge.

Each pass opens its database context (phase 2, S1; plan 2026-10-22): the tasks and the relay run on phase 1's shared
database (``use_shared_database``: every hub with ``db_name=""``; a hub with its own database waits for S2's
``hub_due`` loop), and the reaper on control (``use_control``), where the registry and the demos live.
"""

import datetime as dt
import logging
import threading
from collections.abc import Callable

from django.db import close_old_connections
from django.utils import timezone

from base import catalog, outbound, relay, scheduler
from base.services import reap_demos
from base.tenancy.context import use_control, use_shared_database

logger = logging.getLogger(__name__)

#: How often the loop looks for work; a stop request wakes it up at once.
TICK_SECONDS = 5.0
#: The waits while the SaaS has not migrated ``shared`` yet: they double, 5 s first, 60 s at most.
RETRY_FIRST_SECONDS = 5
RETRY_MAX_SECONDS = 60
#: How often the demo reaper purges the demos that ended (their hosts answer 410 from their end anyway).
REAPER_INTERVAL_SECONDS = 60
#: What the calls in flight (``base.outbound``) get when the worker stops: ECS kills the task 30 s after SIGTERM, and
#: the loop's step ends first. What still runs then is left to its lease.
OUTBOUND_GRACE_SECONDS = 15


def run(
    stop: threading.Event,
    *,
    tick_seconds: float = TICK_SECONDS,
    wait: Callable[[float], object] | None = None,
    clock: Callable[[], dt.datetime] = timezone.now,
) -> int:
    """Register the apps, schedule their tasks, then run the due ones every tick until ``stop`` is set;
    return the process's exit code.

    ``wait(seconds)`` sleeps until the time is up or a stop is requested: ``stop.wait`` unless a
    test replaces it. ``stop`` alone says whether to stop. ``clock()`` is now (a test's fake clock).
    """
    wait = stop.wait if wait is None else wait
    delay = RETRY_FIRST_SECONDS
    while True:
        try:
            result = catalog.register_apps()
            break
        except catalog.SharedSchemaNotReady as error:
            logger.warning(
                "worker: shared schema not migrated yet; retrying in %d s (%s).",
                delay,
                error,
            )
        except Exception:
            logger.exception(
                "worker: register_apps failed; the worker stops (no release without its apps)."
            )
            return 1
        # The SaaS's database is not held open while it waits.
        close_old_connections()
        wait(delay)
        if stop.is_set():
            logger.info("worker: stopped before registering its apps.")
            return 0
        delay = min(delay * 2, RETRY_MAX_SECONDS)
    try:
        with use_shared_database():
            scheduler.sync(clock())
    except Exception:
        logger.exception("worker: the apps' scheduled tasks could not be scheduled; the worker stops.")
        return 1
    # register_apps' connection (the SaaS's database) and sync's are not kept open while it idles.
    close_old_connections()
    if result.skipped:
        registered = "a newer release had already registered its apps"
    else:
        registered = f"{result.written} app(s) registered: {', '.join(result.apps)}"
    logger.info("worker: waiting for work (%s).", registered)
    next_reap: dt.datetime | None = None
    while not stop.is_set():
        now = clock()
        _tick(now)
        _relay(now)
        if next_reap is None or now >= next_reap:
            _reap(now)
            next_reap = now + dt.timedelta(seconds=REAPER_INTERVAL_SECONDS)
        wait(tick_seconds)
    outbound.stop(OUTBOUND_GRACE_SECONDS)
    logger.info("worker: stopped.")
    return 0


def _reap(now: dt.datetime) -> None:
    """Purge the demos that ended by ``now``; a failure is logged and the next pass tries again."""
    try:
        with use_control():
            purged = reap_demos(now)
    except Exception:
        logger.exception("worker: the demo reaper failed; its next pass tries again.")
    else:
        if purged:
            logger.info("worker: purged %d demo(s).", purged)
    finally:
        # The reaper's connection is not kept open while the worker idles, nor a broken one taken further.
        close_old_connections()


def _relay(now: dt.datetime) -> None:
    """Relay the outbox at ``now``; a failure is logged and the next tick tries again."""
    try:
        with use_shared_database():
            done = relay.run(now)
    except Exception:
        logger.exception("worker: the outbox relay failed; the next tick tries again.")
        # A broken connection is not taken into the next tick.
        close_old_connections()
        return
    if done.taken or done.delivered or done.failed:
        logger.debug(
            "worker: relayed %d event(s): %d delivery(ies) done, %d failed.", done.taken, done.delivered, done.failed
        )


def _tick(now: dt.datetime) -> None:
    """Run the scheduled tasks due at ``now``; a failure is logged and the next tick tries again."""
    try:
        with use_shared_database():
            ran = scheduler.run_due(now)
    except Exception:
        logger.exception("worker: the scheduled tasks could not run; the next tick tries again.")
        # A broken connection is not taken into the next tick.
        close_old_connections()
        return
    if ran:
        logger.debug("worker: ran %s.", ", ".join(ran))
