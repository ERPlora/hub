"""The worker's loop (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

It registers the Hub's modules in the SaaS first: without its apps registered there is no release
(round 16, PLAN §21.1.1), so it does no work before that. A ``shared`` schema the SaaS has not
migrated yet (the first deploy) is waited for, with a warning and a backoff of 5, 10, 20, 40 and
then 60 s; any other failure stops the worker with 1. Then it names, as an error, each ready business still without
its own database (S5: it never serves one) and, on every tick until asked to stop (waking up at once: ECS gives it
30 s after SIGTERM), takes control's own outbox (``relay.run(of_hubs=False)``, round 2026-10-20) and serves each hub
with its own database (``_hubs``: its outbox and its tasks, in it; ``test_worker_hubs.py``). A pass that fails is
logged and the next tick tries again. On the first tick and then every ``REAPER_INTERVAL_SECONDS`` it purges the demos
that ended (``reap_demos``, plan 2026-10-17 §1.7); a reaper that fails is logged and never stops the worker. Every
tick it makes the databases of the hubs due in ``hub_due`` and drops the demos that ended (``provision.run_due``,
round 2026-10-30, S2a), on control; a pass that fails is logged and the next tick tries again. No database here:
``register_apps``, the scheduler, the relay, the reaper, the registry and the due pass are replaced; their own tests
are ``test_register_apps.py``, ``test_scheduler.py``, ``test_relay.py``, ``test_services_demo.py`` and
``base/tenancy/tests/test_provision.py``.
"""


import datetime as dt
import logging
import threading
import time

import pytest
from django.db import DatabaseError

from base import catalog, outbound, relay, scheduler, worker
from base.catalog import CatalogError, RegisterResult, SharedSchemaNotReady
from base.tenancy import context, provision

pytestmark = pytest.mark.production_worker

WRITTEN = RegisterResult(written=1, retired=0, docs_changed=1, skipped=False, apps=("demo",))
SKIPPED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
NOT_READY = SharedSchemaNotReady(["shared.app", "shared.app_doc"])
#: The loop's tick in these tests: no retry waits that long.
TICK = 0.5


class FakeScheduler:
    """Stands in for ``scheduler.sync`` and ``scheduler.run_due``: records the clock each one was given."""

    def __init__(self) -> None:
        self.synced: list[dt.datetime] = []
        self.ticks: list[dt.datetime] = []
        self.failures: list[Exception] = []

    def sync(self, now: dt.datetime) -> None:
        self.synced.append(now)

    def run_due(self, now: dt.datetime) -> list[str]:
        self.ticks.append(now)
        if self.failures:
            raise self.failures.pop(0)
        return ["verifactu.process_queue"]


class FakeReaper:
    """Stands in for ``reap_demos``: records the clock of each pass, and raises the failures it is given."""

    def __init__(self) -> None:
        self.passes: list[dt.datetime] = []
        self.failures: list[Exception] = []

    def __call__(self, now: dt.datetime) -> int:
        self.passes.append(now)
        if self.failures:
            raise self.failures.pop(0)
        return 1


class FakeRelay:
    """Stands in for ``relay.run``: records the clock of each pass and whose events it took, and raises the failures
    it is given."""

    def __init__(self) -> None:
        self.passes: list[dt.datetime] = []
        self.of_hubs: list[bool] = []
        self.failures: list[Exception] = []

    def __call__(self, now: dt.datetime, *, of_hubs: bool = True) -> relay.RelayPass:
        self.passes.append(now)
        self.of_hubs.append(of_hubs)
        if self.failures:
            raise self.failures.pop(0)
        return relay.RelayPass(taken=1, delivered=2, failed=0)


class FakeDue:
    """Stands in for ``provision.run_due``: records the clock and the database context of each pass, and raises the
    failures it is given."""

    def __init__(self) -> None:
        self.passes: list[dt.datetime] = []
        self.contexts: list[str] = []
        self.failures: list[Exception] = []

    def __call__(self, now: dt.datetime) -> int:
        self.passes.append(now)
        self.contexts.append(context.current().kind)
        if self.failures:
            raise self.failures.pop(0)
        return 1


@pytest.fixture(autouse=True)
def hubs_pass(monkeypatch) -> list[dt.datetime]:
    """Stands in for the pass over the hubs with their own database (``worker._hubs``; ``test_worker_hubs.py``)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(worker, "_hubs", passes.append)
    return passes


#: The worker's own runner of its slow passes, a thread each (the tests of the loop's order run them inline).
THREADED = worker.Background


class Inline:
    """Stands in for ``worker.Background``: the piece runs at once, in the loop's own thread, so the order is exact."""

    def __init__(self, name: str) -> None:
        self.name = name

    def busy(self) -> bool:
        return False

    def start(self, piece) -> bool:
        piece()
        return True

    def join(self, timeout: float) -> bool:
        return True


@pytest.fixture(autouse=True)
def inline_passes(monkeypatch) -> None:
    monkeypatch.setattr(worker, "Background", Inline)


@pytest.fixture(autouse=True)
def activations_pass(monkeypatch) -> list[dt.datetime]:
    """Stands in for the pass making the tables of the apps turned on (``worker._activations``;
    ``test_worker_activations.py``)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(worker, "_activations", passes.append)
    return passes


@pytest.fixture(autouse=True)
def data_pass(monkeypatch) -> list[dt.datetime]:
    """Stands in for the data pass (``worker._data``: a reset, a business that left; ``test_worker_data.py``)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(worker, "_data", lambda now, stop=None: passes.append(now))
    return passes


@pytest.fixture(autouse=True)
def usage_pass(monkeypatch) -> list[dt.datetime]:
    """Stands in for the nightly measurement's pass (``worker._usage``; ``test_usage.py``)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(worker, "_usage", passes.append)
    return passes


@pytest.fixture(autouse=True)
def moves_pass(monkeypatch) -> list[dt.datetime]:
    """Stands in for the moves' pass (``worker._moves``: a hub moved to another cluster; ``base/tenancy/tests/test_move.py``)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(worker, "_moves", lambda now, stop=None: passes.append(now))
    return passes


@pytest.fixture(autouse=True)
def due(monkeypatch) -> FakeDue:
    fake = FakeDue()
    monkeypatch.setattr(provision, "run_due", fake)
    return fake


@pytest.fixture(autouse=True)
def outbox(monkeypatch) -> FakeRelay:
    fake = FakeRelay()
    monkeypatch.setattr(relay, "run", fake)
    return fake


@pytest.fixture(autouse=True)
def reaper(monkeypatch) -> FakeReaper:
    fake = FakeReaper()
    monkeypatch.setattr(worker, "reap_demos", fake)
    return fake


@pytest.fixture(autouse=True)
def nobody_without_a_database(monkeypatch) -> list:
    """Stands in for the registry's businesses still on control's database (``services.hubs_on_control``), read once at
    start: none here (``test_it_names_each_ready_business_without_its_own_database``)."""
    waiting: list = []
    monkeypatch.setattr(worker.services, "hubs_on_control", lambda: waiting)
    return waiting


@pytest.fixture(autouse=True)
def tasks(monkeypatch) -> FakeScheduler:
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "sync", fake.sync)
    monkeypatch.setattr(scheduler, "run_due", fake.run_due)
    return fake


def ten(minute: int) -> dt.datetime:
    return dt.datetime(2026, 10, 15, 10, minute, tzinfo=dt.UTC)


def clock(*minutes: int):
    """A clock that answers 10:<minute> UTC, one call after another."""
    pending = [ten(minute) for minute in minutes]
    return lambda: pending.pop(0)


@pytest.fixture
def calls(monkeypatch):
    """What the worker did, in order: ``register_apps`` and the release of its connections."""
    done: list[str] = []

    def register_apps() -> RegisterResult:
        done.append("register_apps")
        return WRITTEN

    monkeypatch.setattr(catalog, "register_apps", register_apps)
    monkeypatch.setattr(
        worker, "close_old_connections", lambda: done.append("close_old_connections")
    )
    return done


def stopped() -> threading.Event:
    stop = threading.Event()
    stop.set()
    return stop


def test_registers_the_apps_then_stops_with_0_when_asked(calls):
    assert worker.run(stopped()) == 0

    assert calls[0] == "register_apps"


def test_releases_the_connections_register_apps_opened_before_idling(calls):
    worker.run(stopped())

    assert calls == ["register_apps", "close_old_connections"]


@pytest.mark.parametrize(
    ("result", "said"),
    [(WRITTEN, "1 app(s) registered: demo"), (SKIPPED, "a newer release had already registered its apps")],
    ids=["written", "skipped"],
)
def test_says_what_it_registered_once_it_waits_for_work(monkeypatch, caplog, result, said):
    monkeypatch.setattr(catalog, "register_apps", lambda: result)

    with caplog.at_level(logging.INFO, logger="base.worker"):
        worker.run(stopped())

    assert f"worker: waiting for work ({said})." in caplog.messages


def test_wakes_up_as_soon_as_it_is_asked_to_stop(calls):
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()

    assert worker.run(stop, tick_seconds=60) == 0
    assert time.monotonic() - started < 5


def registrations(monkeypatch, *outcomes):
    """``register_apps`` answering ``outcomes`` in order (an exception is raised); returns its calls."""
    pending, attempts = list(outcomes), []

    def register_apps() -> RegisterResult:
        attempts.append(len(attempts) + 1)
        outcome = pending.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(catalog, "register_apps", register_apps)
    return attempts


def recorded_waits(stop: threading.Event, *, stop_on=TICK):
    """Stands in for ``stop.wait``: records every wait; one of ``stop_on`` seconds asks to stop."""
    waits: list[float] = []

    def wait(seconds: float) -> bool:
        waits.append(seconds)
        if stop_on is None or seconds == stop_on:
            stop.set()
        return stop.is_set()

    return wait, waits


def warnings_of(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "base.worker" and r.levelno == logging.WARNING]


def test_waits_for_the_saas_to_migrate_the_shared_schema_then_works(monkeypatch, caplog):
    attempts = registrations(monkeypatch, NOT_READY, NOT_READY, WRITTEN)
    stop = threading.Event()
    wait, waits = recorded_waits(stop)

    with caplog.at_level(logging.INFO, logger="base.worker"):
        code = worker.run(stop, tick_seconds=TICK, wait=wait)

    assert code == 0
    assert attempts == [1, 2, 3]
    # Two retries (5 s, then 10), then the loop's first tick: it only works once registered.
    assert waits == [5, 10, TICK]
    assert warnings_of(caplog) == [
        f"worker: shared schema not migrated yet; retrying in {seconds} s ({NOT_READY})."
        for seconds in (5, 10)
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert caplog.messages.index("worker: waiting for work (1 app(s) registered: demo).") > caplog.messages.index(
        warnings_of(caplog)[-1]
    )


def test_the_backoff_doubles_up_to_60_seconds(monkeypatch):
    registrations(monkeypatch, *[NOT_READY] * 6, WRITTEN)
    stop = threading.Event()
    wait, waits = recorded_waits(stop)

    assert worker.run(stop, tick_seconds=TICK, wait=wait) == 0
    assert waits == [5, 10, 20, 40, 60, 60, TICK]


def test_releases_the_connection_between_attempts(monkeypatch):
    attempts = registrations(monkeypatch, NOT_READY, WRITTEN)
    released: list[int] = []
    monkeypatch.setattr(worker, "close_old_connections", lambda: released.append(len(attempts)))
    stop = threading.Event()
    wait, _ = recorded_waits(stop)

    worker.run(stop, tick_seconds=TICK, wait=wait)

    # The SaaS's database is not held open while it waits, nor while it idles, nor after the reaper's first pass and
    # the hub_due pass.
    assert released == [1, 2, 2, 2]


def test_a_stop_while_it_waits_for_the_schema_exits_0_without_working(monkeypatch, caplog):
    attempts = registrations(monkeypatch, NOT_READY)
    stop = threading.Event()
    wait, waits = recorded_waits(stop, stop_on=5)  # SIGTERM during the first retry's wait

    with caplog.at_level(logging.INFO, logger="base.worker"):
        code = worker.run(stop, tick_seconds=TICK, wait=wait)

    assert code == 0
    assert (attempts, waits) == ([1], [5])
    assert not any(m.startswith("worker: waiting for work") for m in caplog.messages)
    assert "worker: stopped before registering its apps." in caplog.messages


def test_the_real_wait_wakes_up_as_soon_as_it_is_asked_to_stop(monkeypatch):
    # Without an injected wait: the 5 s retry is ``stop.wait``, which a stop request cuts short.
    registrations(monkeypatch, NOT_READY)
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()

    assert worker.run(stop) == 0
    assert time.monotonic() - started < 4


@pytest.mark.parametrize(
    "failure",
    [
        CatalogError("The 'shared' database alias is not configured"),
        # The tables exist but lack a column: a contract gap (spec §3.5), never waited for.
        CatalogError("the database has no column shared.app.verticals: migrate the SaaS first"),
        DatabaseError("could not connect to server"),
        RuntimeError("unexpected"),
    ],
    ids=["catalog", "column", "database", "anything-else"],
)
def test_a_failed_registration_is_fatal_and_never_retried(monkeypatch, caplog, failure):
    attempts = registrations(monkeypatch, failure)
    stop = threading.Event()
    # A worker that retried, or went on to its loop, would stop here with 0.
    wait, waits = recorded_waits(stop, stop_on=None)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        code = worker.run(stop, tick_seconds=TICK, wait=wait)

    assert code == 1
    assert (attempts, waits) == ([1], [])
    assert not stop.is_set()
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert record.levelno == logging.ERROR
    assert "register_apps" in record.getMessage()
    assert record.exc_info[1] is failure


# ── The scheduled tasks ────────────────────────────────────────────────────────────────────────


def stop_after(stop: threading.Event, ticks: int):
    """Stands in for ``stop.wait``: the ``ticks``-th wait asks to stop; returns the waits it saw."""
    waits: list[float] = []

    def wait(seconds: float) -> bool:
        waits.append(seconds)
        if len(waits) == ticks:
            stop.set()
        return stop.is_set()

    return wait, waits


def test_the_loop_runs_no_task_of_its_own_each_hub_runs_its_own_in_its_pass(calls, tasks, hubs_pass):
    """Since S5 there is no shared database to run every hub's tasks on: each hub's run in its own database, in the
    pass over the hubs (``_serve_hub``, ``test_worker_hubs.py``), every tick."""
    stop = threading.Event()
    wait, waits = stop_after(stop, 3)

    assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1, 2)) == 0

    assert (tasks.synced, tasks.ticks) == ([], [])
    assert hubs_pass == [ten(0), ten(1), ten(2)]
    assert waits == [TICK] * 3


def test_the_ticks_start_once_the_apps_are_registered(monkeypatch, hubs_pass):
    registrations(monkeypatch, NOT_READY, WRITTEN)
    stop = threading.Event()
    wait, waits = recorded_waits(stop)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0))

    # The 5 s retry serves nothing; the first tick, after it, serves the hubs.
    assert waits == [5, TICK]
    assert hubs_pass == [ten(0)]


def test_a_stop_before_registering_serves_nothing(monkeypatch, hubs_pass):
    registrations(monkeypatch, NOT_READY)
    stop = threading.Event()
    wait, _ = recorded_waits(stop, stop_on=5)

    assert worker.run(stop, tick_seconds=TICK, wait=wait) == 0
    assert hubs_pass == []


def test_on_its_way_out_it_gives_the_calls_in_flight_their_grace_within_ecss_30_seconds(calls, monkeypatch):
    # A call to another system a reaction left (base.outbound) may be running: it gets its grace, what waited is
    # dropped and their apps send them again (their lease); then the process ends, before ECS kills it.
    stops: list[float] = []
    monkeypatch.setattr(outbound, "stop", lambda grace: stops.append(grace) or True)

    assert worker.run(stopped()) == 0

    assert stops == [worker.OUTBOUND_GRACE_SECONDS]
    assert 0 < worker.OUTBOUND_GRACE_SECONDS < 30


def test_a_worker_that_never_worked_has_no_calls_to_wait_for(monkeypatch):
    stops: list[float] = []
    monkeypatch.setattr(outbound, "stop", lambda grace: stops.append(grace) or True)
    registrations(monkeypatch, CatalogError("no shared schema user"))

    assert worker.run(stopped()) == 1
    assert stops == []


def test_stop_ends_the_ticks(calls, hubs_pass):
    assert worker.run(stopped()) == 0

    # Asked to stop before its first tick: registered, nothing served.
    assert calls == ["register_apps", "close_old_connections"]
    assert hubs_pass == []


@pytest.mark.parametrize("status", ["ready", "cancelled"])
def test_it_names_each_ready_business_without_its_own_database_as_an_error_and_goes_on(
    caplog, calls, hubs_pass, nobody_without_a_database, status
):
    """S5: a business still on control's database (phase 1's, not cut) is never served: at start the worker says so,
    as an error, for each ready one, and serves the rest; one that left (``cancelled``) is no error, it is made one if
    it comes back."""
    from types import SimpleNamespace

    from control.models import Hub

    nobody_without_a_database.append(SimpleNamespace(slug="elpa", status=Hub.Status(status)))
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0)) == 0

    said = [record for record in caplog.records if record.name == "base.worker" and record.levelno == logging.ERROR]
    if status == "ready":
        [record] = said
        assert "base.worker.hub_without_database hub=elpa" in record.getMessage()
        assert "cut_shared_hubs" in record.getMessage()
    else:
        assert said == []
    assert hubs_pass == [ten(0)]


# ── The demo reaper (plan 2026-10-17, §1.7) ─────────────────────────────────────────────────────


def at(*seconds: int):
    """A clock that answers 10:00 UTC plus ``seconds``, one call after another (one a tick)."""
    pending = [ten(0) + dt.timedelta(seconds=second) for second in seconds]
    return lambda: pending.pop(0)


def test_reaps_the_demos_on_the_first_tick_then_every_minute(calls, reaper):
    stop = threading.Event()
    wait, _ = stop_after(stop, 6)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=at(0, 30, 59, 60, 119, 120))

    second = dt.timedelta(seconds=1)
    assert reaper.passes == [ten(0), ten(0) + 60 * second, ten(0) + 120 * second]
    assert worker.REAPER_INTERVAL_SECONDS == 60


def test_a_stop_before_the_first_tick_reaps_nothing(calls, reaper):
    worker.run(stopped())

    assert reaper.passes == []


def test_releases_the_connection_after_each_pass_of_the_reaper(calls, monkeypatch):
    monkeypatch.setattr(worker, "reap_demos", lambda now: calls.append("reap_demos") or 0)
    monkeypatch.setattr(provision, "run_due", lambda now: calls.append("run_due") or 0)
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0))

    assert calls == [
        "register_apps",
        "close_old_connections",
        "reap_demos",
        "close_old_connections",
        "run_due",
        "close_old_connections",
    ]


def test_a_reaper_that_fails_is_logged_and_never_stops_the_worker(monkeypatch, caplog, calls, hubs_pass, reaper):
    failure = DatabaseError("server closed the connection unexpectedly")
    reaper.failures.append(failure)
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1, 2)) == 0

    # It tries again a minute later, and the hubs were served on every tick all along.
    assert reaper.passes == [ten(0), ten(1), ten(2)]
    assert hubs_pass == [ten(0), ten(1), ten(2)]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "demo" in record.getMessage() and record.exc_info[1] is failure


# ── The outbox relay (round 2026-10-20) ──────────────────────────────────────────────────────────


def test_takes_control_s_own_outbox_on_every_tick_never_a_business_s(calls, outbox):
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1, 2))

    assert outbox.passes == [ten(0), ten(1), ten(2)]
    # On control: the registry's and the demos' events; a business's are relayed in its own database (_serve_hub).
    assert outbox.of_hubs == [False] * 3


def test_a_stop_before_the_first_tick_relays_nothing(calls, outbox):
    worker.run(stopped())

    assert outbox.passes == []


def test_a_relay_pass_that_fails_is_logged_and_the_next_tick_tries_again(caplog, calls, hubs_pass, reaper, outbox):
    failure = DatabaseError("server closed the connection unexpectedly")
    outbox.failures.append(failure)
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1)) == 0

    assert outbox.passes == [ten(0), ten(1)]
    # The hubs and the reaper did not wait for it.
    assert hubs_pass == [ten(0), ten(1)]
    assert reaper.passes == [ten(0), ten(1)]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "control's outbox" in record.getMessage() and record.exc_info[1] is failure
    # Its broken connection is released before the next tick: after registering, after the failed pass, and after
    # each of the reaper's and the hub_due pass's two passes.
    assert calls.count("close_old_connections") == 6


# ── The hubs due: their databases made, the demos that ended dropped (round 2026-10-30, S2a) ───────────────────────


def test_takes_control_s_outbox_then_relays_the_hubs_own_then_makes_the_hubs_due_on_every_tick(
    monkeypatch, calls, tasks, due, outbox
):
    """Review of hub#471 (I2, C1): the relay first, so a slow pass making databases never holds kitchen, stock or
    VeriFactu back; then the hubs with their own database, each relayed in it; the hubs due last, on control. A hub
    made ready in a tick has its outbox relayed from the next one."""
    order: list[str] = []
    monkeypatch.setattr(provision, "run_due", lambda now: order.append("due") or due(now))
    monkeypatch.setattr(relay, "run", lambda now, of_hubs=True: order.append("relay") or outbox(now, of_hubs=of_hubs))
    monkeypatch.setattr(worker, "_hubs", lambda now: order.append("hubs"))
    monkeypatch.setattr(worker, "_activations", lambda now: order.append("activations"))
    monkeypatch.setattr(worker, "_data", lambda now, stop=None: order.append("data"))
    monkeypatch.setattr(worker, "_usage", lambda now: order.append("usage"))
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1, 2))

    assert due.passes == [ten(0), ten(1), ten(2)]
    assert due.contexts == [context.CONTROL] * 3
    # The apps turned on whose tables a hub lacks (S3) right after its own pass, before the hubs due. The slow passes
    # (the data work, the nightly measurement) are started where the loop is in this order, run inline here (Inline); in the worker they run in threads of their own, so nothing orders them against the hubs due: a
    # reset's row the provisioning's pass takes first is given back still due (release_hub, test_worker_data.py).
    assert order == ["relay", "hubs", "activations", "data", "usage", "due"] * 3


def test_with_databases_only_it_makes_the_hubs_databases_and_apps_tables_and_drops_the_demos_and_nothing_else(
    monkeypatch, calls, tasks, due, outbox
):
    """The e2e's worker (tests/e2e/global-setup.ts): its specs play the relay and the tasks themselves, so it only makes
    the databases of the hubs signed up during the run and drops the demos that ended."""
    order: list[str] = []
    monkeypatch.setattr(scheduler, "run_due", lambda now: order.append("tasks") or [])
    monkeypatch.setattr(provision, "run_due", lambda now: order.append("due") or due(now))
    monkeypatch.setattr(relay, "run", lambda now, of_hubs=True: order.append("relay") or outbox(now, of_hubs=of_hubs))
    monkeypatch.setattr(worker, "_hubs", lambda now: order.append("hubs"))
    monkeypatch.setattr(worker, "_reap", lambda now: order.append("reap"))
    monkeypatch.setattr(worker, "_activations", lambda now: order.append("activations"))
    monkeypatch.setattr(worker, "_data", lambda now, stop=None: order.append("data"))
    monkeypatch.setattr(worker, "_usage", lambda now: order.append("usage"))
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1), databases_only=True)

    # Every tick makes the tables of the apps turned on (S3: an app turned on in a spec is set up) and the databases
    # due; the reaper keeps its own pace; nothing else runs.
    assert [step for step in order if step != "reap"] == ["activations", "due", "activations", "due"]
    assert not {"tasks", "relay", "hubs", "data", "usage"} & set(order)


def test_a_due_pass_that_fails_is_logged_and_the_next_tick_tries_again(caplog, calls, hubs_pass, due, outbox):
    failure = DatabaseError("server closed the connection unexpectedly")
    due.failures.append(failure)
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 1)) == 0

    assert due.passes == [ten(0), ten(1)]
    # The hubs and the relay did not wait for it.
    assert hubs_pass == [ten(0), ten(1)] and outbox.passes == [ten(0), ten(1)]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "hub_due" in record.getMessage() and record.exc_info[1] is failure


def test_a_stop_before_the_first_tick_makes_no_hub(calls, due):
    worker.run(stopped())

    assert due.passes == []



def test_the_pass_that_makes_databases_gives_the_next_tick_its_turn():
    """Re-review of hub#471 (c): the hubs due take at most a few seconds a tick (the rest waits for the next), so the
    next tick's relay and the hubs' tasks are never held back long."""
    assert provision.DUE_PASS_SECONDS <= worker.TICK_SECONDS


# ── The slow passes run off the loop (PLAN-DB round 2026-10-31b, C8) ──────────────────────────────────────────────


def test_a_slow_data_pass_never_holds_the_relay_the_tasks_nor_the_hubs_due(monkeypatch, calls, hubs_pass, due, outbox):
    """A copy takes minutes (base.tenancy.dumps): it runs in a thread of its own, one at a time, while the loop keeps
    relaying the events, running the tasks and making the hubs' databases every tick."""
    monkeypatch.setattr(worker, "Background", THREADED)
    release = threading.Event()
    started: list[dt.datetime] = []

    def slow(now, stop=None):
        started.append(now)
        release.wait(10)

    monkeypatch.setattr(worker, "_data", slow)
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    def waiting(seconds):
        stopped = wait(seconds)
        if stopped:
            release.set()  # the copy ends: run waits for it on its way out
        return stopped

    assert worker.run(stop, tick_seconds=TICK, wait=waiting, clock=clock(0, 1, 2)) == 0

    assert due.passes == [ten(0), ten(1), ten(2)]
    assert outbox.passes == [ten(0), ten(1), ten(2)]
    assert hubs_pass == [ten(0), ten(1), ten(2)]
    # One copy at a time: the next tick does not start a second one while the first runs.
    assert started == [ten(0)]


def test_a_data_pass_hears_the_stop_and_the_worker_waits_for_it(monkeypatch, calls):
    monkeypatch.setattr(worker, "Background", THREADED)
    ended: list[str] = []

    def stoppable(now, stop=None):
        stop.wait(10)  # a copy polling its stop: it kills pg_dump and gives its lease back
        ended.append("given back")

    monkeypatch.setattr(worker, "_data", stoppable)
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0)) == 0

    assert ended == ["given back"]


def test_a_pass_that_does_not_end_is_waited_for_a_while_only(monkeypatch, calls, caplog):
    monkeypatch.setattr(worker, "Background", THREADED)
    monkeypatch.setattr(worker, "BACKGROUND_GRACE_SECONDS", 0.2)
    stuck = threading.Event()
    monkeypatch.setattr(worker, "_usage", lambda now: stuck.wait(10))
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)
    started = time.monotonic()

    with caplog.at_level(logging.WARNING, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0)) == 0

    assert time.monotonic() - started < 5
    assert "still running on the way out" in caplog.text
    stuck.set()


def test_a_slow_pass_that_fails_is_logged_and_the_next_tick_starts_it_again(monkeypatch, calls, caplog):
    monkeypatch.setattr(worker, "Background", THREADED)
    runs: list[dt.datetime] = []

    def failing(now, stop=None):
        runs.append(now)
        raise RuntimeError("the database went away")

    monkeypatch.setattr(worker, "_data", failing)
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    def settled(seconds):
        time.sleep(0.2)  # the failed pass ends before the next tick looks
        return wait(seconds)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        worker.run(stop, tick_seconds=TICK, wait=settled, clock=clock(0, 1))

    assert runs == [ten(0), ten(1)]
    assert "the data pass failed" in caplog.text


# ── A hub moved to another cluster (round 2026-10-30b of PLAN-DB, decision 3; base.tenancy.move) ────────────────────


def test_the_moves_run_in_a_thread_of_their_own_every_tick_after_the_data_and_before_the_hubs_due(
    monkeypatch, calls, tasks, due, outbox
):
    order: list[str] = []
    started: list[str] = []

    class Recorded(Inline):
        def start(self, piece) -> bool:
            started.append(self.name)
            return super().start(piece)

    monkeypatch.setattr(worker, "Background", Recorded)
    monkeypatch.setattr(provision, "run_due", lambda now: order.append("due") or due(now))
    monkeypatch.setattr(worker, "_hubs", lambda now: order.append("hubs"))
    monkeypatch.setattr(worker, "_data", lambda now, stop=None: order.append("data"))
    monkeypatch.setattr(worker, "_usage", lambda now: order.append("usage"))
    monkeypatch.setattr(worker, "_moves", lambda now, stop=None: order.append("moves"))
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1))

    assert order == ["hubs", "data", "usage", "moves", "due"] * 2
    assert started == ["data", "usage", "move"] * 2


def test_with_databases_only_no_hub_moves(monkeypatch, calls, tasks, due, outbox, moves_pass):
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1), databases_only=True)

    assert moves_pass == []


def test_the_moves_pass_runs_on_control_and_hears_the_stop(monkeypatch):
    from base.tenancy import move

    monkeypatch.undo()
    seen: list[tuple[str, bool]] = []
    stop = threading.Event()

    def run_due(now, *, cancelled):
        seen.append((context.current().kind, cancelled()))
        stop.set()
        seen.append((context.current().kind, cancelled()))
        return 1

    monkeypatch.setattr(move, "run_due", run_due)

    worker._moves(ten(0), stop)

    assert seen == [(context.CONTROL, False), (context.CONTROL, True)]


def test_a_moves_pass_that_fails_is_logged_and_the_next_tick_tries_again(monkeypatch, caplog):
    from base.tenancy import move

    monkeypatch.undo()
    failure = DatabaseError("server closed the connection unexpectedly")

    def run_due(now, *, cancelled):
        raise failure

    monkeypatch.setattr(move, "run_due", run_due)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        worker._moves(ten(0), threading.Event())

    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "move" in record.getMessage() and record.exc_info[1] is failure
