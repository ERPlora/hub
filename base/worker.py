"""The Hub's worker (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

``manage.py run_worker`` runs it in the ``worker`` task, one per deploy. It first registers the
Hub's modules in the SaaS's registry (round 16, PLAN §21.1.1): without its apps registered there is
no release, so it does no work before that. Two cases (first production deploy, 2026-10-14):

- the SaaS has not migrated the ``shared`` schema yet (``SharedSchemaNotReady``: its tables do not
  exist): transient, so it warns and retries after 5, 10, 20, 40 and then every 60 s, running and
  without working, so ECS sees a stable task; a stop request during the wait exits 0;
- any other failure, a missing column included (a contract gap, spec §3.5): fatal, 1, and ECS's
  ``task_failed`` rule reports it.

Then it names, as an error, each ready business still without a database of its own (phase 1's, not cut yet: S5,
``manage.py cut_shared_hubs``): it never serves one, nor runs it on control. Every tick (5 s), each hub with its own
database gets its outbox relayed (``base.relay``, round 2026-10-20 of PLAN-HUB: each new event to the reactions of the
apps that listen to it, exactly once, in the scope of the hub that recorded it) and the tasks of its apps that are due
run (``scheduler.run_due``: the VeriFactu queue every minute, VERIFACTU-F20, and every other ``scheduled_tasks`` an
app declares, each claimed with ``SKIP LOCKED``; its schedule written in its database once per process); control's own
outbox (the registry's and the demos' events, which no app hears) is taken on control. A pass that fails (the database
went away) is logged and the next tick tries again; a stop request ends the loop at once. What a reaction or a task
leaves for after its COMMIT that waits on the network (a call to another system) runs off this loop, in
``base.outbound``'s threads, so it never holds the next delivery nor the next task; on its way out the worker gives
what still runs ``OUTBOUND_GRACE_SECONDS`` and drops what waits (their lease sends them again). On the first tick and
then every ``REAPER_INTERVAL_SECONDS`` it also purges the demo hubs that ended (``base.services.reap_demos``, plan
2026-10-17 §1.7), whatever the scheduler did: a pass that fails is logged and the next one tries again, and the worker
never stops for it.

After the hubs with their own database, the apps they turned on whose tables they lack (S3; PLAN-DB §7 and §8,
``_activations``, also with ``databases_only``): the hubs rung (``hub_due`` come and free: ``base.app.enable`` rings
after its COMMIT, a retry at its time, the sweep), for ``ACTIVATION_PASS_SECONDS`` at most: in each one, what is due
(``creating``, or ``failed`` past its next try) gets its tables from ``base.tenancy.migrator.ensure_schema(hub, add=…)``
under the hub's schema lock, and ``base.app.activation_settle`` turns it on (its event, its live notice) or ``failed``
with why, and moves the hub's ring to the next of its apps to set up (or ends it); a schema held elsewhere puts it off
30 s, and a request of a newer code than this worker's (``AppActivation.target``, or the app or what it needs already at
a migration this code does not know: a deploy rolling) is left to a worker of that code, 60 s, and fails as
``code_behind`` after 10 minutes (a rollback: none is coming). The pass over ``hub_due`` leaves a ready hub's ring to
it. A ring lost is found by the pass over the hubs served (``_hubs``), which looks into each ready one for apps still to
set up every 10 minutes when it had a visit in the last 7 days, and once a day otherwise.

Then two slow passes of the data (round 2026-10-30 of PLAN-DB, S2b), each in a
thread of its own (:class:`Background`, one piece at a time, its own connections closed when it ends; PLAN-DB round
2026-10-31b, C8): the loop starts them and goes on, so a copy of minutes never holds the relay, the tasks, VeriFactu or
the hubs due. ``_data`` takes one hub with data work due (``base.services.claim_next_data_hub``, under its lease): a reset asked (its database copied by
``base.tenancy.dumps``, then, only if the copy was kept, its sections emptied by ``base.hub.reset_apply`` in its
database) or the copy of a business that left (tried again later when it fails); ``_usage`` measures the last UTC day
once it ended (``base.usage``, 00:15 UTC, before the SaaS collects it at 01:15; once a night whichever worker claims it).
Neither runs with ``databases_only``. On the way out the worker waits for them :data:`BACKGROUND_GRACE_SECONDS` at most:
a copy hears the stop, kills ``pg_dump`` and gives its lease back, and its work stays due. A third thread moves the hubs
asked to move to another cluster and drops the copies they left behind after their days (``_moves``,
``base.tenancy.move``, round 2026-10-30b of PLAN-DB, decision 3), likewise.

The order of a tick (review of hub#471): control's own outbox first; then the hubs with their own database
(``_hubs``, round 2026-10-30 of PLAN-DB): each one it serves (ready, or a business that left but keeps its database,
whose records still to send must reach the AEAT), in its own database (``use_hub``) and one at a time, gets its outbox
relayed, its apps' schedule written there once per process and the tasks due of its active apps run on its own scope
(``host``, its slug: their live notices go on its channel), for ``HUB_PASS_SECONDS`` at most, the next tick going on
after the last hub served; a hub that fails is logged and the others are served. Then the reaper, and last the hubs
whose ``hub_due`` has come: their databases made, the demos that ended dropped (``base.tenancy.provision.run_due``; it
takes no new hub after ``provision.DUE_PASS_SECONDS``, though a clone it started finishes); a hub made ready in a tick
has its outbox relayed from the next one. Every pass releases its connections.

Each pass opens its database context (phase 2, S1; plan 2026-10-22): each hub with its own database in its own
(``use_hub``), and control's outbox, the reaper and the ``hub_due`` pass on control (``use_control``), where the
registry and the demos live (the provisioning enters each hub's own database itself). Since S5 there is no shared
database: a business without its own is never entered.

Its CloudWatch metrics (``base.metrics``, hub#488), only where ``METRICS_ENABLED`` is on, are one more slow pass in a
thread of its own (``Background("metrics")``), started on the first tick and then once a minute of its clock, also with
``databases_only``: the registry's (a sign-up still being prepared, the hubs that failed, a demo left to drop) and the
fiscal backlog. On the way out it shares the others' grace, ending before its next hub.
"""

import datetime as dt
import logging
import threading
import time
from collections.abc import Callable
from functools import cache

from functools import partial

from django.db import close_old_connections
from django.utils import timezone

from live.context import OperationContext, Scope
from live.operations import get as get_operation

from base import activation, catalog, metrics, outbound, queries, relay, scheduler, services, usage
from base.services import reap_demos
from base.tenancy import dumps, migrator, move, provision
from base.tenancy.connections import close_hub_aliases, close_this_threads_connections
from base.schemas import AppActivationSettleIn, HubResetApplyIn
from base.tenancy.context import use_control, use_hub
from control.models import Hub, HubDump

logger = logging.getLogger(__name__)

#: How often the loop looks for work; a stop request wakes it up at once.
TICK_SECONDS = 5.0
#: The waits while the SaaS has not migrated ``shared`` yet: they double, 5 s first, 60 s at most.
RETRY_FIRST_SECONDS = 5
RETRY_MAX_SECONDS = 60
#: How often the demo reaper purges the demos that ended (their hosts answer 410 from their end anyway).
REAPER_INTERVAL_SECONDS = 60
#: How long the pass over the hubs with their own database may go on in a tick; the next tick goes on from the next hub.
HUB_PASS_SECONDS = 3.0
#: The hubs whose schedule this process already wrote in their database (once per process: a release restarts it).
_synced: set = set()
#: The id of the last hub the pass served: the next pass starts after it, so every hub gets its turn.
_next_hub = None
#: How long the worker waits on its way out for its slow passes, all together (ECS kills the task 30 s after SIGTERM,
#: and the calls in flight get OUTBOUND_GRACE_SECONDS after them).
BACKGROUND_GRACE_SECONDS = 10.0
#: The last night this process measured (``base.usage``): the next tick checks the registry again only for a newer one.
_measured: dt.date | None = None
#: How long the lease of a hub whose sections are being emptied lasts (its copy renews a lease of a minute while it
#: runs; the emptying is one transaction of the hub's that does not renew it).
EMPTYING_LEASE = dt.timedelta(minutes=15)
#: What the calls in flight (``base.outbound``) get when the worker stops: ECS kills the task 30 s after SIGTERM, and
#: the loop's step ends first. What still runs then is left to its lease.
OUTBOUND_GRACE_SECONDS = 15
#: How long the pass making the tables of the apps turned on may go on in a tick; a hub it started is always finished,
#: and the next tick goes on after it.
ACTIVATION_PASS_SECONDS = 10.0
#: How often the pass over the hubs served (``_hubs``) looks into a hub for apps to set up whose ring was lost (between a
#: COMMIT and its ring, or ended by another pass): an active one (a visit in the last 7 days) every 10 minutes, any
#: other once a day (PLAN-DB §8, «barrido de reconciliación»).
SWEEP_ACTIVE = dt.timedelta(minutes=10)
SWEEP_ALL = dt.timedelta(days=1)
ACTIVE_WINDOW = dt.timedelta(days=7)
#: How long it waits for a hub's schema another run holds before putting the app off (``SchemaLocked``).
ACTIVATION_LOCK_WAIT = 1.0
#: When the sweep of the hubs served last looked into each one for apps to set up (``_serve_hub``), by hub id.
_swept: dict = {}


def run(
    stop: threading.Event,
    *,
    tick_seconds: float = TICK_SECONDS,
    wait: Callable[[float], object] | None = None,
    clock: Callable[[], dt.datetime] = timezone.now,
    databases_only: bool = False,
) -> int:
    """Register the apps, schedule their tasks, then run the due ones every tick until ``stop`` is set;
    return the process's exit code.

    ``wait(seconds)`` sleeps until the time is up or a stop is requested: ``stop.wait`` unless a
    test replaces it. ``stop`` alone says whether to stop. ``clock()`` is now (a test's fake clock).
    ``databases_only`` (``run_worker --databases-only``, the e2e's worker): only the hubs' databases are made, the
    tables of the apps they turn on made (S3) and the demos that ended dropped; no task runs and no outbox is relayed,
    which the e2e's specs play themselves.
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
    _name_the_businesses_without_a_database()
    # register_apps' connection (the SaaS's database) and the registry's are not kept open while it idles.
    close_old_connections()
    if result.skipped:
        registered = "a newer release had already registered its apps"
    else:
        registered = f"{result.written} app(s) registered: {', '.join(result.apps)}"
    logger.info("worker: waiting for work (%s).", registered)
    emitter = metrics.emitter(stop)
    next_reap: dt.datetime | None = None
    # The slow passes, each in a thread of its own and one at a time: the loop keeps ticking while they run.
    data_pass, usage_pass, metrics_pass = Background("data"), Background("usage"), Background("metrics")
    # A hub's move to another cluster (base.tenancy.move): its copy takes a while too, in a thread of its own.
    move_pass = Background("move")
    while not stop.is_set():
        now = clock()
        if not databases_only:
            _relay(now)
            _hubs(now)
        _activations(now)
        if not databases_only:
            data_pass.start(partial(_data, now, stop))
            usage_pass.start(partial(_usage, now))
            move_pass.start(partial(_moves, now, stop))
        emitter.start_due(now, metrics_pass)
        if next_reap is None or now >= next_reap:
            _reap(now)
            next_reap = now + dt.timedelta(seconds=REAPER_INTERVAL_SECONDS)
        _due(now)
        wait(tick_seconds)
    # On the way out: a copy hears the stop (pg_dump killed, its lease given back), a metrics pass ends before its next
    # hub; they all get a while, together.
    deadline = time.monotonic() + BACKGROUND_GRACE_SECONDS
    for runner in (data_pass, usage_pass, move_pass, metrics_pass):
        runner.join(max(0.0, deadline - time.monotonic()))
    outbound.stop(OUTBOUND_GRACE_SECONDS)
    logger.info("worker: stopped.")
    return 0


class Background:
    """One slow pass at a time in a thread of its own (PLAN-DB round 2026-10-31b, C8): the data pass, whose copy of a
    hub's database may take minutes, the nightly measurement and the CloudWatch metrics (``base.metrics``). The loop
    starts it when it is not running and goes on with its tick; a piece that fails is logged and the next tick starts it
    again. Each piece opens its own connections (the thread starts with no database context: the passes enter theirs)
    and closes all of them when it ends."""

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


def _due(now: dt.datetime) -> None:
    """Make the databases of the hubs due by ``now`` and drop the demos that ended; a failure is logged and the next
    tick tries again (each hub's own failure is noted on it by the provisioning)."""
    try:
        with use_control():
            worked = provision.run_due(now)
    except Exception:
        logger.exception("worker: the hub_due pass failed; the next tick tries again.")
    else:
        if worked:
            logger.info("worker: worked on %d hub(s) due.", worked)
    finally:
        # The pass's connections (control's, and each hub's direct one) are not kept open while the worker idles.
        close_old_connections()


def _hubs(now: dt.datetime) -> None:
    """Relay the outbox and run the due tasks of the hubs with their own database, each in it, one at a time, for
    :data:`HUB_PASS_SECONDS` at most; the next tick goes on after the last one served. A hub that fails is logged and
    the others are served."""
    global _next_hub
    try:
        with use_control():
            hubs = services.hubs_to_serve(now)
            active = services.hubs_visited_since((now - ACTIVE_WINDOW).date()) if hubs else frozenset()
    except Exception:
        logger.exception("worker: the hubs to serve could not be read; the next tick tries again.")
        close_old_connections()
        return
    if not hubs:
        return
    start = next((index for index, hub in enumerate(hubs) if _next_hub is not None and hub.pk > _next_hub), 0)
    started = time.monotonic()
    for hub in hubs[start:] + hubs[:start]:
        _serve_hub(hub, now, active=hub.slug in active)
        _next_hub = hub.pk
        if time.monotonic() - started > HUB_PASS_SECONDS:
            break


def _activations(now: dt.datetime) -> None:
    """Make the tables of the apps due in the hubs rung (their ``hub_due`` came: an app turned on or tried again, a
    retry's time, a ring of the sweep), for :data:`ACTIVATION_PASS_SECONDS` at most; a hub that fails is logged and the
    others are served."""
    try:
        with use_control():
            rung = services.activation_hubs(now)
    except Exception:
        logger.exception("worker: the hubs with apps to set up could not be read; the next tick tries again.")
        close_old_connections()
        return
    started = time.monotonic()
    for hub in rung:
        _activate(hub, now)
        if time.monotonic() - started > ACTIVATION_PASS_SECONDS:
            return


def _activate(hub, now: dt.datetime) -> None:
    """The apps due in ``hub`` set up (:func:`_activate_in`); a failure is logged, its connections released either way."""
    try:
        _activate_in(hub, now)
    except Exception:
        logger.exception("worker: the apps of %s could not be set up; the next pass tries again.", hub.slug)
    finally:
        close_hub_aliases(hub)
        close_old_connections()


def _activate_in(hub, now: dt.datetime) -> None:
    """Read what is due in ``hub``'s database; make its tables, unless the request or the database is of a newer code
    than this worker's; settle the rows with how it went."""
    with use_hub(hub):
        due = queries.activations_due(hub.slug, now)
        if not due:
            # Rung for nothing due now (a retry still to come, or nothing left): its ring moves to what is next, or ends.
            services.activations_rung_at(hub.pk, queries.activation_next_at(hub.slug))
            return
    apps, error = sorted(due), ""
    code = _code()
    newer = sorted(label for label, target in due.items() if target and (label, target) not in code.nodes)
    # Only what it makes counts: the platform or another app of a later code (a rollback) never holds it back, as the
    # migrator ignores what it does not know (PLAN-DB §7, «Rollback»).
    making = set(apps) | activation.needs(apps, activation.module_graph())
    ahead = sorted(
        label
        for label, name in (hub.schema_apps or {}).items()
        if label in making and label in code.leaves and (label, name) not in code.nodes
    )
    if newer or ahead:
        outcome = "newer_code"
        logger.warning(
            "base.app.activation_newer_code hub=%s apps=%s: asked by (%s) or a database at (%s) a newer code than this "
            "worker's; left to a worker of that code.",
            hub.slug, ",".join(apps), ",".join(newer) or "-", ",".join(ahead) or "-",
        )
    else:
        try:
            migrator.ensure_schema(hub, add=apps, lock_wait=ACTIVATION_LOCK_WAIT)
            outcome = "created"
        except migrator.SchemaLocked:
            outcome = "locked"
        except Exception as failure:
            outcome, error = "failed", f"{type(failure).__name__}: {failure}"
            logger.exception("worker: the tables of %s could not be made in %s.", ",".join(apps), hub.slug)
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language="en")
    with use_control():
        hub = services.registry_row(hub.pk)
    with use_hub(hub):
        get_operation("base.app.activation_settle")(ctx, AppActivationSettleIn(apps=apps, outcome=outcome, error=error))


@cache
def _code() -> migrator.CodeMigrations:
    """This code's migration graph (its leaves and nodes): it never changes while the process runs."""
    return migrator.code_migrations()


def _data(now: dt.datetime, stop: threading.Event | None = None) -> None:
    """The data work of one hub due by ``now``, under its lease (round 2026-10-30 of PLAN-DB, decision 2 and proposal
    (a)): a reset asked (its database copied, then its sections emptied) or the copy of a business that left. It runs in
    the worker's data thread (:class:`Background`), one hub at a time: a copy takes a while, and the loop goes on
    meanwhile. A failure is logged and the work stays due (a lease lost is left to its holder); ``stop`` set stops the
    copy in course (``pg_dump`` killed), its lease given back and the work left due for the next worker."""
    try:
        with use_control():
            hub_id = services.claim_next_data_hub(now, provision.LEASE)
    except Exception:
        logger.exception("worker: the hubs with data work could not be read; the next tick tries again.")
        close_old_connections()
        return
    if hub_id is None:
        return
    try:
        with use_control():
            hub = services.registry_row(hub_id)
            cancelled = stop.is_set if stop is not None else None
            if hub is not None and hub.reset_requested_at is not None:
                _reset(hub, cancelled)
            elif hub is not None and services.offboarding_due(hub):
                _offboarding_copy(hub, now, cancelled)
    except dumps.DumpStopped:
        logger.info("worker: the copy of the hub %s was stopped with the worker; it stays due.", hub_id)
    except Exception:
        logger.exception("worker: the data work of the hub %s failed; it is tried again.", hub_id)
    finally:
        try:
            with use_control():
                services.release_hub(hub_id, timezone.now())
        except Exception:
            logger.exception("worker: the lease of the hub %s could not be given back; it runs out by itself.", hub_id)
        row = services.registry_row(hub_id) if hub_id else None
        if row is not None and row.db_name:
            close_hub_aliases(row)
        close_old_connections()


def _usage(now: dt.datetime) -> None:
    """Measure the last UTC day that ended (``base.usage``: 00:15, once a night, whichever worker claims it); a failure
    is logged and the next tick tries again."""
    global _measured
    day = usage.day_due(now)
    if _measured is not None and _measured >= day:
        return
    try:
        with use_control():
            measured = None if services.usage_ready(day) else usage.measure(day, now=now)
            finished = measured is not None or services.usage_ready(day)
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


def _moves(now: dt.datetime, stop: threading.Event | None = None) -> None:
    """Move the hub asked longest ago to its new cluster and drop the copies past their days
    (``base.tenancy.move.run_due``, round 2026-10-30b of PLAN-DB, decision 3), on control, in the worker's move thread
    (:class:`Background`); a failure is logged and the next tick tries again. ``stop`` set stops the copy in course and
    leaves the move for the next worker to go on."""
    try:
        with use_control():
            moved = move.run_due(now, cancelled=stop.is_set if stop is not None else None)
    except Exception:
        logger.exception("worker: the moves' pass failed; the next tick tries again.")
    else:
        if moved:
            logger.info("worker: worked on the move of %d hub(s).", moved)
    finally:
        close_old_connections()


def _heartbeat(hub) -> Callable[[], None]:
    return lambda: services.renew_lease(hub.pk, provision.LEASE)


def _reset(hub, cancelled: Callable[[], bool] | None = None) -> None:
    """Copy the database of ``hub`` and, only if the copy was kept, empty the sections asked; each step noted."""
    asked = hub.reset_sections or {}
    if hub.status != Hub.Status.READY or not hub.db_name:
        services.reset_moved(hub.pk, state="failed", error="hub_not_ready")
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
        services.reset_moved(hub.pk, state="failed", error=failed.code)
        return
    services.reset_moved(hub.pk, state="emptying", dump=str(copy.pk))
    services.renew_lease(hub.pk, EMPTYING_LEASE)
    ctx = OperationContext(
        scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}), language=asked.get("language") or "en"
    )
    try:
        with use_hub(hub):
            done = get_operation("base.hub.reset_apply")(ctx, HubResetApplyIn(apps=asked.get("apps") or []))
    except Exception:
        logger.exception("worker: the sections of %s could not be emptied; its copy is kept, nothing was emptied.", hub.slug)
        services.reset_moved(hub.pk, state="failed", error="emptying_failed")
        return
    services.reset_moved(hub.pk, state="done", removed=[app.model_dump(mode="json") for app in done.apps])
    logger.info("worker: the business %s was reset (%s) after its copy %s.", hub.slug, ", ".join(asked.get("apps") or []), copy.key)


def _offboarding_copy(hub, now: dt.datetime, cancelled: Callable[[], bool] | None = None) -> None:
    """Copy the database of the business ``hub`` that left; a failure is tried again at its next attempt."""
    try:
        dumps.dump_hub(hub, kind=HubDump.Kind.OFFBOARDING, heartbeat=_heartbeat(hub), cancelled=cancelled)
    except dumps.DumpError as failed:
        logger.warning("worker: the copy of %s, which left, failed; it is tried again: %s", hub.slug, failed)
        services.offboarding_copy_failed(hub.pk, now, f"{failed.code}: {failed}")
        return
    services.offboarding_copied(hub.pk)


def _serve_hub(hub, now: dt.datetime, *, active: bool = False) -> None:
    """One hub's outbox relayed and its due tasks run, in its own database and on its own scope; its schedule written
    there first, once per process; and, at the sweep's pace (``active``: a visit in the last 7 days), a ready hub with
    apps still to set up rung again (a ring lost). A failure is logged; its connections are released either way."""
    scope = Scope("host", hub.slug)
    try:
        with use_hub(hub):
            if hub.pk not in _synced:
                scheduler.sync(now)
                _synced.add(hub.pk)
            relay.run(now)
            scheduler.run_due(now, scope=scope, active=relay.active_apps(scope))
            if hub.status == Hub.Status.READY and _sweep_due(hub.pk, now, active):
                _swept[hub.pk] = now
                pending = queries.activation_next_at(hub.slug)
                if pending is not None:
                    services.ring_activations(hub, pending)
    except Exception:
        logger.exception("worker: the hub %s failed; the next tick tries it again.", hub.slug)
    finally:
        close_hub_aliases(hub)
        close_old_connections()


def _sweep_due(hub_id, now: dt.datetime, active: bool) -> bool:
    last = _swept.get(hub_id)
    return last is None or now - last >= (SWEEP_ACTIVE if active else SWEEP_ALL)


def _relay(now: dt.datetime) -> None:
    """Take control's own outbox at ``now`` (the registry's and the demos' events: no app hears them); a failure is
    logged and the next tick tries again. A hub's events are relayed in its own database (:func:`_serve_hub`)."""
    try:
        with use_control():
            done = relay.run(now, of_hubs=False)
    except Exception:
        logger.exception("worker: control's outbox could not be taken; the next tick tries again.")
        # A broken connection is not taken into the next tick.
        close_old_connections()
        return
    if done.taken or done.delivered or done.failed:
        logger.debug(
            "worker: relayed %d event(s): %d delivery(ies) done, %d failed.", done.taken, done.delivered, done.failed
        )


def _name_the_businesses_without_a_database() -> None:
    """Log, as an error, each ready business still without a database of its own (phase 1's, not cut yet): since S5
    the worker never serves one, nor runs it on control, and its host answers 503 until ``manage.py cut_shared_hubs``
    gives it one. A business that left (``cancelled``) without one is no error: it is made one if it comes back."""
    try:
        with use_control():
            waiting = [hub.slug for hub in services.hubs_on_control() if hub.status == Hub.Status.READY]
    except Exception:
        logger.exception("worker: the businesses without a database of their own could not be read.")
        return
    for slug in waiting:
        logger.error(
            "base.worker.hub_without_database hub=%s: it has no database of its own and is not served; run "
            "manage.py cut_shared_hubs (docs/runbooks/cut-shared-hubs.md).",
            slug,
        )
