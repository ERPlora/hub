"""The worker's loop, phase 1 (CLAUDE.md «Procesos»; aws-next README, «Contrato app ↔ infra»).

It registers the Hub's modules in the SaaS first: without its apps registered there is no release
(round 16, PLAN §21.1.1), so any failure there stops the worker with 1. Then it waits until asked
to stop, waking up at once: ECS gives it 30 s after SIGTERM. No database here: ``register_apps``
is replaced, and its own tests are ``test_register_apps.py``.
"""

import logging
import threading
import time

import pytest
from django.db import DatabaseError

from base import catalog, worker
from base.catalog import CatalogError, RegisterResult

WRITTEN = RegisterResult(written=1, retired=0, docs_changed=1, skipped=False, apps=("demo",))
SKIPPED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


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


@pytest.mark.parametrize(
    "failure",
    [
        CatalogError("The 'shared' database alias is not configured"),
        DatabaseError("could not connect to server"),
        RuntimeError("unexpected"),
    ],
    ids=["catalog", "database", "anything-else"],
)
def test_a_failed_registration_is_fatal(monkeypatch, caplog, failure):
    def broken_register_apps():
        raise failure

    monkeypatch.setattr(catalog, "register_apps", broken_register_apps)
    stop = threading.Event()
    # Safety net: a worker that went on to its loop instead would end here, with 0.
    safety = threading.Timer(2, stop.set)
    safety.start()
    try:
        with caplog.at_level(logging.ERROR, logger="base.worker"):
            code = worker.run(stop, tick_seconds=0.01)
    finally:
        safety.cancel()

    assert code == 1
    assert not stop.is_set()
    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert record.levelno == logging.ERROR
    assert "register_apps" in record.getMessage()
    assert record.exc_info[1] is failure
