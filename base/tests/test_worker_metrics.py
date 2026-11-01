"""The worker publishes its CloudWatch metrics without ever holding its tick (hub#488; ``base.metrics``).

Once its apps are registered, the worker builds its emitter (``metrics.emitter``, on its own
stop request) and, every tick, starts a metrics pass when one is due (at once, then once a minute of its clock) in a
thread of its own, ``Background("metrics")``, as its other slow passes (PLAN-DB round 2026-10-31b, C8): a pass that
takes long (a slow database, CloudWatch unreachable) never delays the relay, the tasks, VeriFactu or the hubs due, and
on its way out it shares their grace. A worker that never registered its apps measures nothing. No database here: the
passes of the tick are the fakes of ``test_worker.py``; the metrics' own tests are ``test_metrics.py``.
"""

import datetime as dt
import logging
import threading
import time

import pytest

from base import catalog, metrics, worker
from base.catalog import CatalogError
from base.metrics import Metric
from base.tests.test_metrics import FakeCloudWatch
from base.tests.test_worker import (  # noqa: F401 (the fakes of every pass of the tick, autouse)
    THREADED,
    WRITTEN,
    data_pass,
    due,
    hubs_pass,
    inline_passes,
    outbox,
    reaper,
    tasks,
    usage_pass,
)

START = dt.datetime(2026, 11, 1, 10, 0, tzinfo=dt.UTC)


@pytest.fixture
def registered(monkeypatch) -> None:
    monkeypatch.setattr(catalog, "register_apps", lambda: WRITTEN)
    monkeypatch.setattr(worker, "close_old_connections", lambda: None)


@pytest.fixture
def cloudwatch(settings, monkeypatch) -> FakeCloudWatch:
    """Metrics on, CloudWatch a fake."""
    settings.METRICS_ENABLED = True
    client = FakeCloudWatch()
    monkeypatch.setattr(metrics, "cloudwatch_client", lambda: client)
    return client


def every(seconds: int):
    """A clock that answers START, then ``seconds`` later on each call."""
    calls = iter(range(10_000))
    return lambda: START + dt.timedelta(seconds=seconds * next(calls))


def test_a_pass_runs_at_once_then_once_a_minute_of_the_workers_clock(registered, cloudwatch, monkeypatch):
    def measure(now, stop):
        return [Metric("ERPlora/Hubs", "HubsFailed", 0.0, "Count")]

    monkeypatch.setattr(metrics, "default_collectors", lambda: [measure])
    stop = threading.Event()
    ticks: list[None] = []

    def wait(seconds):
        ticks.append(None)
        if len(ticks) == 6:
            stop.set()

    # Six ticks 30 s apart from 10:00:00 (since S5 no schedule is written before them: each hub's is written in its
    # own database; the passes run inline here, test_worker.inline_passes): a pass on the first tick, then one a minute.
    assert worker.run(stop, wait=wait, clock=every(30)) == 0

    assert [call["MetricData"][0]["Timestamp"] for call in cloudwatch.calls] == [
        START,
        START + dt.timedelta(seconds=60),
        START + dt.timedelta(seconds=120),
    ]


def test_a_slow_metrics_pass_never_holds_the_tick(registered, cloudwatch, monkeypatch, tasks):
    monkeypatch.setattr(worker, "Background", THREADED)
    entered, release = threading.Event(), threading.Event()
    measured_in: list[str] = []

    def slow(now, stop):
        measured_in.append(threading.current_thread().name)
        entered.set()
        release.wait(10)
        return []

    monkeypatch.setattr(metrics, "default_collectors", lambda: [slow])
    stop = threading.Event()
    held: list[bool] = []

    def wait(seconds):
        if not held:
            assert entered.wait(5), "the metrics' first pass never started"
        held.append(not release.is_set())
        if len(held) == 5:
            release.set()
            stop.set()

    assert worker.run(stop, wait=wait, clock=every(30)) == 0

    # Five ticks, each with its tasks run, all while the one metrics pass was still measuring in its own thread.
    assert held == [True] * 5
    assert len(tasks.ticks) == 5
    assert measured_in == ["worker-metrics"]


def test_on_its_way_out_a_metrics_pass_in_course_shares_the_slow_passes_grace(
    registered, cloudwatch, monkeypatch, caplog
):
    monkeypatch.setattr(worker, "Background", THREADED)
    monkeypatch.setattr(worker, "BACKGROUND_GRACE_SECONDS", 0.2)
    entered, release = threading.Event(), threading.Event()

    def stuck(now, stop):
        entered.set()
        release.wait(10)
        return []

    monkeypatch.setattr(metrics, "default_collectors", lambda: [stuck])
    stop = threading.Event()

    def wait(seconds):
        assert entered.wait(5)
        stop.set()

    started = time.monotonic()
    try:
        with caplog.at_level(logging.WARNING, logger="base.worker"):
            assert worker.run(stop, wait=wait) == 0
    finally:
        release.set()

    # Within the slow passes' own grace (ECS kills the task 30 s after SIGTERM), never a wait of its own on top.
    assert time.monotonic() - started < 2
    said = "worker: the metrics pass is still running on the way out"
    assert any(message.startswith(said) for message in caplog.messages)


def test_off_no_metrics_pass_ever_starts(registered, monkeypatch, settings):
    settings.METRICS_ENABLED = False
    monkeypatch.setattr(metrics, "default_collectors", lambda: pytest.fail("no measure while off"))
    stop = threading.Event()
    ticks: list[None] = []

    def wait(seconds):
        ticks.append(None)
        if len(ticks) == 3:
            stop.set()

    assert worker.run(stop, wait=wait, clock=every(60)) == 0


def test_a_worker_that_never_registered_its_apps_measures_nothing(monkeypatch):
    def failing():
        raise CatalogError("contract gap")

    monkeypatch.setattr(catalog, "register_apps", failing)
    monkeypatch.setattr(metrics, "emitter", lambda stop: pytest.fail("no metrics without the apps registered"))

    assert worker.run(threading.Event()) == 1
