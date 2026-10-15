"""Two deliveries at once: real sessions in threads, real row locks (WORKBOOK «Una sola ejecución por
aviso»). The same event handed over twice at the same moment starts one run per automation; two
workers firing the due schedules at once start each one once."""

import datetime as dt
import threading
import uuid
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from live.context import system_context

from apps.flow import events
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task

from .conftest import A, make_flow, run

pytestmark = pytest.mark.django_db(transaction=True)

MADRID = ZoneInfo("Europe/Madrid")


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # reported to the test, which fails on it
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_the_same_event_delivered_twice_at_once_runs_once():
    first = make_flow("First")
    second = make_flow("Second")
    event_id = uuid.uuid7()
    deliver = lambda: events.react(A, "customer.customer.created", {"id": "c"}, event_id=event_id)  # noqa: E731
    results = at_once(deliver, deliver, deliver)
    assert not [result for result in results if isinstance(result, Exception)], results
    # Each automation is started by whichever delivery locked it first; the others skip it.
    assert sum(result.started for result in results) == 2
    assert sum(result.skipped for result in results) == 4
    assert FlowRun.objects.filter(flow=first).count() == 1
    assert FlowRun.objects.filter(flow=second).count() == 1
    assert Task.objects.count() == 2


def test_two_workers_fire_a_due_schedule_once(monkeypatch):
    from django.utils import timezone

    now = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
    monkeypatch.setattr(timezone, "now", lambda: now)
    flow = make_flow(
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
        next_fire_at=dt.datetime(2026, 10, 15, 9, 0, tzinfo=MADRID),
    )
    fire = lambda: run("flow.schedule.fire_due", {}, system_context(A))  # noqa: E731
    results = at_once(fire, fire)
    assert not [result for result in results if isinstance(result, Exception)], results
    assert sum(result.count for result in results) == 1
    assert FlowRun.objects.filter(flow=flow).count() == 1


def test_two_workers_resume_each_waiting_run_once(monkeypatch):
    # Review 2026-10-15, item 8: `resume_due` claims its runs with SKIP LOCKED.
    from django.utils import timezone

    start = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
    monkeypatch.setattr(timezone, "now", lambda: start)
    make_flow(steps=[{"id": "s1", "kind": "delay", "seconds": 60}, {"id": "s2", "kind": "command", "operation": "task.task.create", "params": {"title": "After"}}])
    for n in range(3):
        events.react(A, "customer.customer.created", {"id": str(n)}, event_id=uuid.uuid7())
    assert FlowRun.objects.filter(status=FlowRun.Status.WAITING).count() == 3
    monkeypatch.setattr(timezone, "now", lambda: start + dt.timedelta(minutes=2))
    resume = lambda: run("flow.run.resume_due", {}, system_context(A))  # noqa: E731
    results = at_once(resume, resume)
    assert not [result for result in results if isinstance(result, Exception)], results
    assert sum(result.count for result in results) == 3
    assert FlowRun.objects.filter(status=FlowRun.Status.SUCCEEDED).count() == 3
    assert Task.objects.filter(title="After").count() == 3
