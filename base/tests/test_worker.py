"""The worker's loop, phase 1 (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

It registers the Hub's modules in the SaaS first: without its apps registered there is no release
(round 16, PLAN §21.1.1), so it does no work before that. A ``shared`` schema the SaaS has not
migrated yet (the first deploy) is waited for, with a warning and a backoff of 5, 10, 20, 40 and
then 60 s; any other failure stops the worker with 1. Then it schedules the apps' tasks once
(``scheduler.sync``; a failure there is fatal too) and, on every tick, runs the ones that are due
(``scheduler.run_due``) until asked to stop, waking up at once: ECS gives it 30 s after SIGTERM. A
tick that fails is logged and the next one tries again. On the first tick and then every
``REAPER_INTERVAL_SECONDS`` it purges the demos that ended (``reap_demos``, plan 2026-10-17 §1.7); a reaper that
fails is logged and never stops the worker. Every tick, after the tasks, it relays the outbox (``relay.run``, round
2026-10-20); a relay pass that fails is logged and the next tick tries again. No database here: ``register_apps``,
the scheduler, the relay and the reaper are replaced; their own tests are ``test_register_apps.py``,
``test_scheduler.py``, ``test_relay.py`` and ``test_services_demo.py``.
"""

import datetime as dt
import logging
import threading
import time

import pytest
from django.db import DatabaseError

from base import catalog, relay, scheduler, worker
from base.catalog import CatalogError, RegisterResult, SharedSchemaNotReady

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
    """Stands in for ``relay.run``: records the clock of each pass, and raises the failures it is given."""

    def __init__(self) -> None:
        self.passes: list[dt.datetime] = []
        self.failures: list[Exception] = []

    def __call__(self, now: dt.datetime) -> relay.RelayPass:
        self.passes.append(now)
        if self.failures:
            raise self.failures.pop(0)
        return relay.RelayPass(taken=1, delivered=2, failed=0)


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

    # The SaaS's database is not held open while it waits, nor while it idles, nor after the reaper's first pass.
    assert released == [1, 2, 2]


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


def test_schedules_the_apps_tasks_once_then_runs_the_due_ones_on_every_tick(calls, tasks):
    stop = threading.Event()
    wait, waits = stop_after(stop, 3)

    assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1, 2)) == 0

    assert tasks.synced == [ten(0)]
    assert tasks.ticks == [ten(0), ten(1), ten(2)]
    assert waits == [TICK] * 3


def test_the_ticks_start_once_the_apps_are_registered(monkeypatch, tasks):
    registrations(monkeypatch, NOT_READY, WRITTEN)
    stop = threading.Event()
    wait, waits = recorded_waits(stop)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0))

    # The 5 s retry runs nothing; the first tick, after it, runs the due tasks.
    assert waits == [5, TICK]
    assert len(tasks.synced) == len(tasks.ticks) == 1


def test_a_stop_before_registering_schedules_nothing(monkeypatch, tasks):
    registrations(monkeypatch, NOT_READY)
    stop = threading.Event()
    wait, _ = recorded_waits(stop, stop_on=5)

    assert worker.run(stop, tick_seconds=TICK, wait=wait) == 0
    assert (tasks.synced, tasks.ticks) == ([], [])


def test_stop_ends_the_ticks(calls, tasks):
    assert worker.run(stopped()) == 0

    # Asked to stop before its first tick: the tasks are scheduled, none runs.
    assert len(tasks.synced) == 1
    assert tasks.ticks == []


def test_a_failure_to_schedule_the_tasks_is_fatal(monkeypatch, caplog, calls, tasks):
    failure = DatabaseError("relation base_taskschedule does not exist")

    def sync(now):
        raise failure

    monkeypatch.setattr(scheduler, "sync", sync)
    stop = threading.Event()
    wait, waits = recorded_waits(stop, stop_on=None)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait) == 1

    assert (tasks.ticks, waits) == ([], [])
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "scheduled tasks" in record.getMessage()
    assert record.exc_info[1] is failure


def test_a_tick_that_fails_is_logged_and_the_next_one_tries_again(monkeypatch, caplog, calls, tasks):
    failure = DatabaseError("server closed the connection unexpectedly")
    tasks.failures.append(failure)
    stop = threading.Event()
    wait, waits = stop_after(stop, 2)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1)) == 0

    assert len(tasks.ticks) == 2
    assert waits == [TICK, TICK]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "next tick" in record.getMessage()
    assert record.exc_info[1] is failure
    # The broken connection is released before the next tick: after registering, after the failed tick, and after
    # each of the reaper's two passes (10:00 and 10:01).
    assert calls.count("close_old_connections") == 4


# ── The demo reaper (plan 2026-10-17, §1.7) ─────────────────────────────────────────────────────


def at(*seconds: int):
    """A clock that answers 10:00 UTC plus ``seconds``, one call after another (the first is the scheduler's)."""
    pending = [ten(0) + dt.timedelta(seconds=second) for second in seconds]
    return lambda: pending.pop(0)


def test_reaps_the_demos_on_the_first_tick_then_every_minute(calls, reaper):
    stop = threading.Event()
    wait, _ = stop_after(stop, 6)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=at(0, 0, 30, 59, 60, 119, 120))

    second = dt.timedelta(seconds=1)
    assert reaper.passes == [ten(0), ten(0) + 60 * second, ten(0) + 120 * second]
    assert worker.REAPER_INTERVAL_SECONDS == 60


def test_a_stop_before_the_first_tick_reaps_nothing(calls, reaper):
    worker.run(stopped())

    assert reaper.passes == []


def test_releases_the_connection_after_each_pass_of_the_reaper(calls, monkeypatch):
    monkeypatch.setattr(worker, "reap_demos", lambda now: calls.append("reap_demos") or 0)
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0))

    assert calls == ["register_apps", "close_old_connections", "reap_demos", "close_old_connections"]


def test_a_reaper_that_fails_is_logged_and_never_stops_the_worker(monkeypatch, caplog, calls, tasks, reaper):
    failure = DatabaseError("server closed the connection unexpectedly")
    reaper.failures.append(failure)
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1, 2)) == 0

    # It tries again a minute later, and the scheduled tasks ran on every tick all along.
    assert reaper.passes == [ten(0), ten(1), ten(2)]
    assert tasks.ticks == [ten(0), ten(1), ten(2)]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "demo" in record.getMessage() and record.exc_info[1] is failure


def test_a_failed_tick_of_the_scheduler_still_reaps(calls, tasks, reaper):
    tasks.failures.append(DatabaseError("deadlock detected"))
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0))

    assert reaper.passes == [ten(0)]


# ── The outbox relay (round 2026-10-20) ──────────────────────────────────────────────────────────


def test_relays_the_outbox_on_every_tick_after_the_tasks(monkeypatch, calls, tasks, outbox):
    order: list[str] = []
    monkeypatch.setattr(scheduler, "run_due", lambda now: order.append("tasks") or [])
    monkeypatch.setattr(relay, "run", lambda now: order.append("relay") or outbox(now))
    stop = threading.Event()
    wait, _ = stop_after(stop, 3)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1, 2))

    assert outbox.passes == [ten(0), ten(1), ten(2)]
    # What a task records is relayed in the same tick.
    assert order == ["tasks", "relay"] * 3


def test_a_stop_before_the_first_tick_relays_nothing(calls, outbox):
    worker.run(stopped())

    assert outbox.passes == []


def test_a_relay_pass_that_fails_is_logged_and_the_next_tick_tries_again(caplog, calls, tasks, reaper, outbox):
    failure = DatabaseError("server closed the connection unexpectedly")
    outbox.failures.append(failure)
    stop = threading.Event()
    wait, _ = stop_after(stop, 2)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0, 1)) == 0

    assert outbox.passes == [ten(0), ten(1)]
    # The tasks and the reaper did not wait for it.
    assert tasks.ticks == [ten(0), ten(1)]
    assert reaper.passes == [ten(0), ten(1)]
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "outbox relay" in record.getMessage() and record.exc_info[1] is failure
    # Its broken connection is released before the next tick: after registering, after the failed pass, and after
    # each of the reaper's two passes.
    assert calls.count("close_old_connections") == 4


def test_a_failed_tick_of_the_scheduler_still_relays(calls, tasks, outbox):
    tasks.failures.append(DatabaseError("deadlock detected"))
    stop = threading.Event()
    wait, _ = stop_after(stop, 1)

    worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(0, 0))

    assert outbox.passes == [ten(0)]
