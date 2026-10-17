"""Two deliveries at once: real sessions in threads, real row locks (WORKBOOK «Una sola ejecución por
aviso»). The same event handed over twice at the same moment starts one run per automation; two
workers firing the due schedules at once start each one once. An automation deleted while it is
being looked up answers what was read or «not found», never a 500 nor a change on the deleted one."""

import datetime as dt
import json
import threading
import uuid
from contextlib import contextmanager
from zoneinfo import ZoneInfo

import pytest
from django.db import connection, transaction
from live.context import system_context
from live.errors import NotFound
from live.models import OutboxEvent
from psycopg.errors import LockNotAvailable

from apps.flow import events
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task

from .conftest import A, TASK_STEP, make_flow, run

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


# An automation deleted while it is being looked up (FIX-FLOW-DETAIL-RACE): the lookup found it and then
# loaded it again by its id, so a deletion committed between the two either raised DoesNotExist (a 500)
# or handed back the automation that was just deleted. Each case lands the deletion there, both the
# business's «Delete» (the row stays, marked deleted) and the Hub admin's (the row goes).

DELETIONS = ["operation", "row"]


def delete(flow, how: str) -> None:
    """Deletes ``flow`` in this session, giving up at once on a row another session has locked. The lock
    timeout is the transaction's (SET LOCAL): a session-level one would go back to the pool with the
    connection and reach the tests after this one (the autouse fixture of conftest.py fails a test that leaves it)."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '300ms'")
        if how == "operation":
            run("flow.flow.delete", {"id": str(flow.id)})
        else:
            # What the Hub admin's «Delete» does: ModelAdmin.delete_model is the row's delete().
            Flow.objects.get(pk=flow.pk).delete()


@contextmanager
def deleted_after_the_first_read_of(flow, how: str):
    """Commits the deletion of ``flow`` in another session right after the first statement of this one
    that reads the automations: a deletion landing in the middle of a lookup, every time."""
    table = f'"{Flow._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(flow, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def outcome(deletions) -> list[str]:
    """«ok» for a deletion that landed, «locked» for one this session's lock kept out."""

    def one(result):
        if not isinstance(result, Exception):
            return "ok"
        cause = result
        while cause is not None and not isinstance(cause, LockNotAvailable):
            cause = cause.__cause__
        return "locked" if cause is not None else repr(result)

    return [one(result) for result in deletions]


def events_since(before: int) -> list[str]:
    return list(OutboxEvent.objects.order_by("id").values_list("name", flat=True)[before:])


@pytest.mark.parametrize("how", DELETIONS)
def test_an_automation_deleted_while_its_detail_is_read_is_never_a_server_error(how):
    flow = make_flow("Welcome")
    with deleted_after_the_first_read_of(flow, how) as deletions:
        detail = run("flow.flow.detail", {"id": str(flow.id)})
    assert outcome(deletions) == ["ok"]
    # The automation as it was read, before the deletion: one moment, never half of each.
    assert (detail.id, detail.name, detail.enabled) == (flow.id, "Welcome", True)
    # What the deletion's event runs next: not found, and the open detail says so.
    with pytest.raises(NotFound) as error:
        run("flow.flow.detail", {"id": str(flow.id)})
    assert (error.value.code, error.value.status) == ("not_found", 404)


@pytest.mark.parametrize("how", DELETIONS)
def test_an_automation_deleted_between_its_name_and_its_detail_is_not_found(how):
    flow = make_flow("Welcome")
    with deleted_after_the_first_read_of(flow, how) as deletions:
        with pytest.raises(NotFound) as error:
            run("flow.flow.detail", {"flow": "welcome"})
    assert (outcome(deletions), error.value.code, error.value.status) == (["ok"], "not_found", 404)


def test_an_automation_deleted_while_it_is_tried_is_never_a_server_error():
    flow = make_flow("Welcome", grants=["task.task.create"])
    data = {"id": str(flow.id), "document": json.dumps({"trigger": {"kind": "manual"}, "steps": [TASK_STEP]})}
    expected = run("flow.flow.test", data)
    with deleted_after_the_first_read_of(flow, "row") as deletions:
        tried = run("flow.flow.test", data)
    # Tried with the permissions it had when it was read.
    assert (outcome(deletions), tried) == (["ok"], expected)


LATE_COMMANDS = [
    ("flow.flow.update", {"name": "Renamed"}),
    ("flow.flow.set_enabled", {"enabled": True}),
    ("flow.flow.grant", {"operations": []}),
    ("flow.flow.duplicate", {}),
    ("flow.flow.delete", {}),
    ("flow.flow.run", {}),
]


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize(("name", "data"), LATE_COMMANDS, ids=[name for name, _ in LATE_COMMANDS])
def test_a_command_on_an_automation_deleted_after_its_name_was_found_is_not_found(name, data, how):
    flow = make_flow("Welcome")
    before = OutboxEvent.objects.count()
    with deleted_after_the_first_read_of(flow, how) as deletions:
        with pytest.raises(NotFound) as error:
            run(name, {"flow": "welcome", **data})
    assert (outcome(deletions), error.value.code, error.value.status) == (["ok"], "not_found", 404)
    # Nothing done on the deleted automation: no copy, no run, no event of the late command.
    assert events_since(before) == (["flow.flow.deleted"] if how == "operation" else [])
    assert [(f.name, f.enabled, f.deleted_at is None) for f in Flow.objects.all()] == (
        [("Welcome", False, False)] if how == "operation" else []
    )
    assert FlowRun.objects.count() == 0


@pytest.mark.parametrize("how", DELETIONS)
def test_a_command_by_id_locks_its_automation_in_the_read_that_finds_it(how):
    flow = make_flow("Welcome")
    with deleted_after_the_first_read_of(flow, how) as deletions:
        renamed = run("flow.flow.update", {"id": str(flow.id), "name": "Renamed"})
    # The deletion arrives once the automation is found, and waits for the edit instead of slipping in
    # before it: the edit is never made on an automation that is already gone.
    assert (outcome(deletions), renamed.name) == (["locked"], "Renamed")
    assert [(f.name, f.deleted_at is None) for f in Flow.objects.all()] == [("Renamed", True)]
