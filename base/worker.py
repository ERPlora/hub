"""The Hub's worker.

``manage.py run_worker`` runs it in the ``worker`` task, one per deploy. It first registers the Hub's modules in the
SaaS's registry: without its apps registered there is no release, so it does no work before that. Two cases:

- the SaaS has not migrated the ``shared`` schema yet (``SharedSchemaNotReady``: its tables do not exist): transient,
  so it warns and retries after 5, 10, 20, 40 and then every 60 s, running and without working, so ECS sees a stable
  task; a stop request during the wait exits 0;
- any other failure, a missing column included (a gap in the contract with the SaaS): fatal, 1, and ECS's
  ``task_failed`` rule reports it.

Then it names, as an error, each ready business still without a database of its own (one that shared a database and was
not cut yet, ``manage.py cut_shared_hubs``): it never serves one, nor runs it on control. Every tick (5 s), the hubs
with their own database that have something to do are visited (``base.hub_visits``: one whose channel was notified after
a COMMIT, whose next task of an app on or next try of a delivery came, or not visited for a minute): its outbox relayed
(``base.relay``: each new event to the reactions of the apps that listen to it, exactly once, in the scope of the hub
that recorded it) and the tasks of its apps that are due run (``scheduler.run_due``: the VeriFactu queue every minute,
and every other ``scheduled_tasks`` an app declares, each claimed with ``SKIP LOCKED``); a hub at rest is not entered
between two of them. Control's own steps run in a pass of their own, only on the ticks ``base.control_pace`` says (a
notice on the platform's channel, a time control keeps, a pass that worked or failed, or its look every minute), and
nothing is sent to control's database between two: its own outbox (the registry's and the demos' events, which no app
hears), the list of hubs the visits serve, and the steps below. A pass that fails (the database went away) is logged and
the next tick tries again; a stop request ends the loop at once. What a reaction or a task leaves for after its COMMIT
that waits on the network (a call to another system) runs off this loop, in ``base.outbound``'s threads, so it never
holds the next delivery nor the next task; on its way out the worker gives what still runs ``OUTBOUND_GRACE_SECONDS``
and drops what waits (their lease sends them again). A pass also purges the demo hubs that ended
(``base.services.demos.reap_demos``), once every ``REAPER_INTERVAL_SECONDS`` at most: a reaper that fails is logged and
never stops the worker.

After the visits, the apps the hubs turned on whose tables they lack (``_activations``, also with ``databases_only``):
the hubs rung (``hub_due`` come and free: ``base.app.enable`` rings after its COMMIT, a retry at its time, the sweep),
for ``ACTIVATION_PASS_SECONDS`` at most: in each one, what is due (``creating``, or ``failed`` past its next try) gets
its tables from ``base.tenancy.migrator.schema.ensure_schema(hub, add=…)`` under the hub's schema lock, and
``base.app.activation_settle`` turns it on (its event, its live notice) or ``failed`` with why, and moves the hub's ring
to the next of its apps to set up (or ends it); a schema held elsewhere puts it off 30 s, and a request of a newer code
than this worker's (``AppActivation.target``, or the app or what it needs already at a migration this code does not
know: a deploy rolling) is left to a worker of that code, 60 s, and fails as ``code_behind`` after 10 minutes (a
rollback: none is coming). The pass over ``hub_due`` leaves a ready hub's ring to it. A ring lost is found by the
visits' sweep (``base.hub_visits``).

Then two slow passes of the data, each in a thread of its own (:class:`Background`, one piece at a time, its own
connections closed when it ends): the loop starts them and goes on, so a copy of minutes never holds the relay, the
tasks, VeriFactu or the hubs due. ``_data`` takes one hub with data work due (``claim_next_data_hub``, under its lease):
a reset asked (its database copied, then, only if the copy was kept, its sections emptied by ``base.hub.reset_apply``),
the copy of a business that left, or, past its 90 days, its final copy and the drop of its database
(``base.tenancy.offboarding``; not while it keeps fiscal documents); ``_usage`` measures the last UTC day once it ended
(``base.usage``, 00:15 UTC; once a night whichever worker claims it). Neither runs with ``databases_only``. A third
thread (``_moves``) moves one hub asked to move to another cluster, restores one from its copy, makes one separate copy
and drops the copies past their days. One that worked or failed has the next tick start it again, for the next hub
waiting. On the way out the worker waits for them :data:`BACKGROUND_GRACE_SECONDS` at most: a copy hears the stop.

Last in a pass, the hubs whose ``hub_due`` has come: their databases made, the demos that ended dropped
(``base.tenancy.provision.run_due``; no new hub after ``provision.DUE_PASS_SECONDS``, though a clone it started
finishes); a hub made ready in a pass is visited from the next tick. Every pass releases its connections. A hub is
entered in its own database (``use_hub``), control's steps run on control (``use_control``): there is no shared one.

Each pass first reads the freeze switch of control, once (``control.queries.active_freeze``: a database upgrade with
Blue/Green copies no DDL). While the staff keeps the platform frozen (``control.freeze.set``, the Hub admin) it starts
nothing that makes, drops or moves a database or makes a table: the apps' tables, the data work, the moves, the reaper
and the hubs due wait, each in its own queue, and are done from the first pass after the freeze is lifted (its notice
wakes one). The relay, every hub's tasks (VeriFactu's queue among them), the nightly measure and the metrics go on. What
started before the freeze ends (its lease held: ``control.freeze.get`` counts them). A switch that cannot be read counts
as frozen for that pass. The change is said once each way.

Its CloudWatch metrics (``base.metrics``), only where ``METRICS_ENABLED`` is on, are one more slow pass in a thread of
its own (``Background("metrics")``), started on the first tick and then once a minute of its clock, also with
``databases_only``: the registry's (a sign-up still being prepared, the hubs that failed, a demo left to drop) and the
fiscal backlog. On the way out it shares the others' grace, ending before its next hub."""

import datetime as dt
import logging
import threading
import time
from collections.abc import Callable
from functools import partial

from django.db import close_old_connections
from django.utils import timezone

from base import catalog, control_pace, hub_visits, metrics, outbound, relay, services
from base.services.demos import reap_demos
from base.tenancy import provision
from base.tenancy.connections import close_this_threads_connections
from base.tenancy.context import use_control
from base.worker_activations import _activations
from base.worker_data import _data, _moves, _usage
from control import queries as control_queries
from control.models.hubs import Hub

logger = logging.getLogger(__name__)

#: How often the loop looks for work; a stop request wakes it up at once.
TICK_SECONDS = 5.0
#: The waits while the SaaS has not migrated ``shared`` yet: they double, 5 s first, 60 s at most.
RETRY_FIRST_SECONDS = 5
RETRY_MAX_SECONDS = 60
#: How often the demo reaper purges the demos that ended (their hosts answer 410 from their end anyway).
REAPER_INTERVAL_SECONDS = 60
#: How long the worker waits on its way out for its slow passes, all together (ECS kills the task 30 s after SIGTERM,
#: and the calls in flight get OUTBOUND_GRACE_SECONDS after them).
BACKGROUND_GRACE_SECONDS = 10.0
#: What the calls in flight (``base.outbound``) get when the worker stops: ECS kills the task 30 s after SIGTERM, and
#: the loop's step ends first. What still runs then is left to its lease.
OUTBOUND_GRACE_SECONDS = 15


def run(
    stop: threading.Event,
    *,
    tick_seconds: float = TICK_SECONDS,
    wait: Callable[[float], object] | None = None,
    clock: Callable[[], dt.datetime] = timezone.now,
    databases_only: bool = False,
) -> int:
    """Register the apps, then run a tick (:class:`Ticks`) every ``tick_seconds`` until ``stop`` is set; return the
    process's exit code.

    ``wait(seconds)`` sleeps until the time is up or a stop is requested: ``stop.wait`` unless a test replaces it.
    ``stop`` alone says whether to stop. ``clock()`` is now (a test's fake clock). ``databases_only`` (``run_worker
    --databases-only``, the e2e's worker): only the hubs' databases are made, the tables of the apps they turn on made
    and the demos that ended dropped; no task runs and no outbox is relayed, which the e2e's specs play themselves.
    """
    wait = stop.wait if wait is None else wait
    result = _register(stop, wait)
    if isinstance(result, int):
        return result
    _name_the_businesses_without_a_database()
    # register_apps' connection (the SaaS's database) and the registry's are not kept open while it idles.
    close_old_connections()
    if result.skipped:
        logger.info("worker: waiting for work (a newer release had already registered its apps).")
    else:
        logger.info("worker: waiting for work (%d app(s) registered: %s).", result.written, ", ".join(result.apps))
    ticks = Ticks(stop, databases_only=databases_only)
    while not stop.is_set():
        ticks.tick(clock())
        wait(tick_seconds)
    ticks.close()
    logger.info("worker: stopped.")
    return 0


def _register(stop: threading.Event, wait: Callable[[float], object]) -> catalog.register_apps.RegisterResult | int:
    """Register the apps, waiting while the SaaS has not migrated ``shared``; the exit code when it ends first."""
    delay = RETRY_FIRST_SECONDS
    while True:
        try:
            return catalog.register_apps.register_apps()
        except catalog.errors.SharedSchemaNotReady as error:
            logger.warning("worker: shared schema not migrated yet; retrying in %d s (%s).", delay, error)
        except Exception:
            logger.exception("worker: register_apps failed; the worker stops (no release without its apps).")
            return 1
        # The SaaS's database is not held open while it waits.
        close_old_connections()
        wait(delay)
        if stop.is_set():
            logger.info("worker: stopped before registering its apps.")
            return 0
        delay = min(delay * 2, RETRY_MAX_SECONDS)


class Ticks:
    """A tick of the loop: the visits, the slow passes it starts and, when their pass is due, control's steps."""

    def __init__(self, stop: threading.Event, *, databases_only: bool) -> None:
        self._stop, self._databases_only = stop, databases_only
        self._emitter = metrics.emitter(stop)
        self._slow = {name: Background(name) for name in ("data", "usage", "move", "metrics")}
        ear = control_pace.Ear()
        self._visits, self._pace = hub_visits.HubVisits(ear), control_pace.ControlPace(ear)
        self._frozen, self._next_reap = False, None

    def tick(self, now: dt.datetime) -> None:
        look = self._pace.due(now)
        if look:
            self._read_the_freeze()
        changes = look and not self._frozen
        worked = False
        if not self._databases_only:
            worked = look and _relay(now)
            self._visits.serve(now, look=look)
        worked = (changes and _activations(now)) or worked
        self._start_the_slow_passes(now, changes)
        if changes:
            worked = self._reap_and_make(now) or worked
        if look:
            self._pace.ran(now, worked=worked)

    def close(self) -> None:
        """The slow passes get a while, together (a copy hears the stop), then the calls in flight theirs."""
        deadline = time.monotonic() + BACKGROUND_GRACE_SECONDS
        for runner in self._slow.values():
            runner.join(max(0.0, deadline - time.monotonic()))
        outbound.stop(OUTBOUND_GRACE_SECONDS)
        self._visits.close()

    def _read_the_freeze(self) -> None:
        frozen = _frozen()
        if frozen and not self._frozen:
            logger.warning(
                "worker: frozen (control.freeze.set): no database is made, dropped or moved and no app's tables are made "
                "until the freeze is lifted; the relay, the tasks and VeriFactu go on."
            )
        elif self._frozen and not frozen:
            logger.info("worker: the freeze was lifted; what waited is done from this pass.")
        self._frozen = frozen

    def _start_the_slow_passes(self, now: dt.datetime, changes: bool) -> None:
        if not self._databases_only:
            if changes:
                self._slow["data"].start(self._pace.telling(partial(_data, now, self._stop)))
            self._slow["usage"].start(partial(_usage, now))
            if changes and self._pace.moves_due(now):
                moves = self._pace.telling(partial(_moves, now, self._stop))
                self._pace.moved(now, started=self._slow["move"].start(moves))
        self._emitter.start_due(now, self._slow["metrics"])

    def _reap_and_make(self, now: dt.datetime) -> bool:
        """The reaper at its pace, then the hubs due; whether these worked or failed."""
        if self._next_reap is None or now >= self._next_reap:
            _reap(now)
            self._next_reap = now + dt.timedelta(seconds=REAPER_INTERVAL_SECONDS)
        return _due(now)


class Background:
    """One slow pass at a time in a thread of its own: the data pass, whose copy of a hub's database may take minutes,
    the nightly measurement and the CloudWatch metrics (``base.metrics``). The loop starts it when it is not running and
    goes on with its tick; a piece that fails is logged and the next tick starts it again. Each piece opens its own
    connections (the thread starts with no database context: the passes enter theirs) and closes all of them when it
    ends."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._thread: threading.Thread | None = None

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, piece: Callable[[], object]) -> bool:
        """Run ``piece`` in a thread of its own unless the last one still runs; whether it started."""
        if self.busy():
            return False
        self._thread = threading.Thread(target=self._run, args=(piece,), name=f"worker-{self.name}", daemon=True)
        self._thread.start()
        return True

    def _run(self, piece: Callable[[], object]) -> None:
        try:
            piece()
        except Exception:
            logger.exception("worker: the %s pass failed; the next tick starts it again.", self.name)
        finally:
            close_this_threads_connections()

    def join(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds for the piece running; whether none runs after."""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        if self._thread.is_alive():
            logger.warning(
                "worker: the %s pass is still running on the way out; its lease runs out and another worker takes it.",
                self.name,
            )
            return False
        return True


def _frozen() -> bool:
    """Whether the platform is frozen (``control.freeze.set``), read once for this pass on control; ``True`` too when
    the switch cannot be read, said in the log: no pass that changes a database starts blind."""
    try:
        with use_control():
            return control_queries.active_freeze() is not None
    except Exception:
        logger.exception("worker: the freeze switch could not be read; this pass makes, drops and moves no database.")
        return True


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


def _due(now: dt.datetime) -> bool:
    """Make the databases of the hubs due by ``now`` and drop the demos that ended; whether it worked on one or failed:
    a failure is logged and the next tick tries again (each hub's own failure is noted on it by the provisioning)."""
    try:
        with use_control():
            worked = provision.run_due(now)
    except Exception:
        logger.exception("worker: the hub_due pass failed; the next tick tries again.")
        return True
    else:
        if worked:
            logger.info("worker: worked on %d hub(s) due.", worked)
    finally:
        # The pass's connections (control's, and each hub's direct one) are not kept open while the worker idles.
        close_old_connections()
    return bool(worked)


def _relay(now: dt.datetime) -> bool:
    """Take control's own outbox at ``now`` (the registry's and the demos' events: no app hears them); whether it
    relayed some or failed: a failure is logged and the next tick tries again. A hub's events are relayed in its own
    database (``base.hub_visits``)."""
    try:
        with use_control():
            done = relay.run(now, of_hubs=False)
    except Exception:
        logger.exception("worker: control's outbox could not be taken; the next tick tries again.")
        # A broken connection is not taken into the next tick.
        close_old_connections()
        return True
    relayed = bool(done.taken or done.delivered or done.failed)
    if relayed:
        logger.debug("worker: relayed %d event(s): %d done, %d failed.", done.taken, done.delivered, done.failed)
    return relayed


def _name_the_businesses_without_a_database() -> None:
    """Log, as an error, each ready business still without a database of its own (one that shared a database and was
    not cut yet): the worker never serves one, nor runs it on control, and its host answers 503 until ``manage.py cut_shared_hubs``
    gives it one. A business that left (``cancelled``) without one is no error: it is made one if it comes back."""
    try:
        with use_control():
            waiting = [hub.slug for hub in services.hub_registry.hubs_on_control() if hub.status == Hub.Status.READY]
    except Exception:
        logger.exception("worker: the businesses without a database of their own could not be read.")
        return
    for slug in waiting:
        logger.error(
            "base.worker.hub_without_database hub=%s: it has no database of its own and is not served; run "
            "manage.py cut_shared_hubs (knowledge/wiki/runbooks/cut-shared-hubs.md).",
            slug,
        )
