"""The worker's loop, phase 1 (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

It registers the Hub's modules in the SaaS first: without its apps registered there is no release
(round 16, PLAN §21.1.1), so it does no work before that. A ``shared`` schema the SaaS has not
migrated yet (the first deploy) is waited for, with a warning and a backoff of 5, 10, 20, 40 and
then 60 s; any other failure stops the worker with 1. Then it waits until asked to stop, waking up
at once: ECS gives it 30 s after SIGTERM. No database here: ``register_apps`` is replaced, and its
own tests are ``test_register_apps.py``.
"""

import logging
import threading
import time

import pytest
from django.db import DatabaseError

from base import catalog, worker
from base.catalog import CatalogError, RegisterResult, SharedSchemaNotReady

WRITTEN = RegisterResult(written=1, retired=0, docs_changed=1, skipped=False, apps=("demo",))
SKIPPED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
NOT_READY = SharedSchemaNotReady(["shared.app", "shared.app_doc"])
#: The loop's tick in these tests: no retry waits that long.
TICK = 0.5


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

    # The SaaS's database is not held open while it waits, nor while it idles.
    assert released == [1, 2]


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
