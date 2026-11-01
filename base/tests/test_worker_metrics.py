"""The worker publishes its CloudWatch metrics without ever holding its tick (hub#488; ``base.metrics``).

Once its apps are registered and their tasks scheduled, the worker starts the metrics' thread (``metrics.start``, on
its own stop request) and, on its way out, gives a pass in course ``METRICS_GRACE_SECONDS`` within ECS's 30 s. A
worker that never registered its apps starts none. A metrics pass that takes long (a slow database, CloudWatch
unreachable) never delays the relay, the tasks, VeriFactu or the hubs due: the ticks go on meanwhile. No database here:
the passes of the tick are the fakes of ``test_worker.py``; the metrics' own tests are ``test_metrics.py``.
"""

import threading

import pytest

from base import catalog, metrics, worker
from base.catalog import CatalogError
from base.tests.test_metrics import FakeCloudWatch
from base.tests.test_worker import (  # noqa: F401 (the fakes of every pass of the tick, autouse)
    WRITTEN,
    due,
    hubs_pass,
    outbox,
    reaper,
    tasks,
)


class FakeEmitter:
    """Stands in for the metrics' thread: records its start and the grace it was given on the way out."""

    def __init__(self, done: list[str]) -> None:
        self.done = done
        self.stop: threading.Event | None = None

    def start(self, stop: threading.Event) -> "FakeEmitter":
        self.stop = stop
        self.done.append("metrics.start")
        return self

    def join(self, timeout: float) -> bool:
        self.done.append(f"metrics.join({timeout})")
        return True


@pytest.fixture
def done(monkeypatch) -> list[str]:
    calls: list[str] = []

    def register_apps():
        calls.append("register_apps")
        return WRITTEN

    monkeypatch.setattr(catalog, "register_apps", register_apps)
    monkeypatch.setattr(worker, "close_old_connections", lambda: None)
    return calls


def test_the_metrics_start_once_the_apps_are_registered_and_get_their_grace_on_the_way_out(monkeypatch, done):
    emitter = FakeEmitter(done)
    monkeypatch.setattr(metrics, "start", emitter.start)
    stop = threading.Event()

    def wait(seconds):
        done.append("tick")
        stop.set()

    assert worker.run(stop, wait=wait) == 0

    assert done == ["register_apps", "metrics.start", "tick", f"metrics.join({worker.METRICS_GRACE_SECONDS})"]
    assert emitter.stop is stop
    # ECS kills the task 30 s after SIGTERM: the metrics' grace and the calls in flight' fit in it.
    assert worker.METRICS_GRACE_SECONDS + worker.OUTBOUND_GRACE_SECONDS < 30


def test_a_worker_that_never_registered_its_apps_starts_no_metrics(monkeypatch):
    def failing():
        raise CatalogError("contract gap")

    monkeypatch.setattr(catalog, "register_apps", failing)
    monkeypatch.setattr(metrics, "start", lambda stop: pytest.fail("no metrics without the apps registered"))

    assert worker.run(threading.Event()) == 1


def test_a_slow_metrics_pass_never_holds_the_tick(settings, monkeypatch, done, tasks):
    settings.METRICS_ENABLED = True
    entered, release = threading.Event(), threading.Event()

    def slow(now, stop):
        entered.set()
        release.wait(10)
        return []

    monkeypatch.setattr(metrics, "default_collectors", lambda: [slow])
    monkeypatch.setattr(metrics, "cloudwatch_client", FakeCloudWatch)
    stop = threading.Event()
    held: list[bool] = []

    def wait(seconds):
        if not held:
            assert entered.wait(5), "the metrics' first pass never started"
        held.append(not release.is_set())
        if len(held) == 5:
            release.set()
            stop.set()

    assert worker.run(stop, wait=wait) == 0

    # Five ticks, each with its tasks run, all while the metrics' pass was still measuring.
    assert held == [True] * 5
    assert len(tasks.ticks) == 5
    assert not any(thread.name == "worker-metrics" and thread.is_alive() for thread in threading.enumerate())
