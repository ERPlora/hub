"""The scheduled tasks of the apps, run by the worker (VERIFACTU-F20; port of the old Hub's
``crates/runtime/src/scheduler.rs`` and its tests).

Every ``LiveAppConfig`` may declare ``scheduled_tasks``: an operation of its own, a five-field cron
read in UTC and ``catch_up = "collapse"``. ``sync`` writes them to ``TaskSchedule`` once per boot,
keeping the clock of the ones it already knew (``seed_module_tasks``); ``run_due`` claims each due row
with ``SKIP LOCKED``, runs its operation as the system on the worker's scope and moves ``next_run`` to
the next time after now in the same transaction: a backlog of missed times collapses into one run
(``catch_up_on_boot``), and a second worker never runs the same row at once. A task that raises is
logged and rescheduled, and the others still run.
"""

import datetime as dt
import logging
import os
import subprocess
import sys
import threading
import types
import zoneinfo

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from live import operations
from live.context import Scope
from live.operations import Operation
from ninja import Schema

from base import scheduler
from base.models import TaskSchedule
from base.scheduler import ScheduledTask

UTC = dt.UTC


def at(hour: int, minute: int, second: int = 0) -> dt.datetime:
    return dt.datetime(2026, 10, 15, hour, minute, second, tzinfo=UTC)


class NoIn(Schema):
    pass


class Done(Schema):
    ok: bool = True


def fake_operation(monkeypatch, name: str, fn, *, kind: str = "command") -> Operation:
    """An operation registered under ``name`` for the test only (``fn(ctx, data)``)."""
    op = Operation(
        name=name,
        kind=kind,
        permission=None,
        input=NoIn,
        output=Done,
        expose_api=False,
        ai=None,
        fn=fn,
    )
    monkeypatch.setitem(operations.registry, name, op)
    return op


def task(name: str, cron: str = "* * * * *", app: str = "test") -> ScheduledTask:
    return ScheduledTask(
        app_label=app,
        name=name,
        operation=f"{app}.task.{name}",
        cron=cron,
        catch_up="collapse",
    )


@pytest.fixture(autouse=True)
def released(monkeypatch) -> list[str]:
    """``run_due`` releases the connections after every task; inside a test's transaction that would
    close it, so here it is only counted (the two-workers test runs the real one)."""
    calls: list[str] = []
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: calls.append("close"))
    return calls


@pytest.fixture
def ticks(monkeypatch):
    """A task ``test.tick`` every minute whose runs are recorded as ``(ctx, data)``."""
    seen: list = []

    def tick(ctx, data):
        seen.append((ctx, data))
        return Done()

    fake_operation(monkeypatch, "test.task.tick", tick)
    return seen


# ── What the apps declare ──────────────────────────────────────────────────────────────────────


def test_the_apps_declare_the_verifactu_queue_every_minute():
    declared = {t.key: t for t in scheduler.tasks()}

    assert declared["verifactu.process_queue"] == ScheduledTask(
        app_label="verifactu",
        name="process_queue",
        operation="verifactu.contingency.process",
        cron="* * * * *",
        catch_up="collapse",
    )


def test_the_tasks_the_apps_declare_pass_the_check():
    assert scheduler.check_scheduled_tasks() == []


def errors_of(*entries) -> list[tuple[str, str]]:
    config = types.SimpleNamespace(label="verifactu", scheduled_tasks=list(entries))
    return [
        (error.id, error.msg) for error in scheduler.scheduled_task_errors([config])
    ]


def entry(**changes) -> dict:
    return {
        "name": "process_queue",
        "operation": "verifactu.contingency.process",
        "cron": "* * * * *",
        "catch_up": "collapse",
        **changes,
    }


@pytest.mark.parametrize(
    "cron",
    ["61 * * * *", "* * * * * *", "", "every minute", "@hourly"],
    ids=["out-of-range", "six-fields", "empty", "words", "shortcut"],
)
def test_a_cron_the_engine_cannot_read_is_refused_by_name(cron):
    [(code, message)] = errors_of(entry(cron=cron))

    assert code == "base.E002"
    assert "verifactu.process_queue" in message


@pytest.mark.parametrize(
    ("operation", "why"),
    [
        ("verifactu.record.nothing", "unknown"),
        ("invoice.invoice.create", "another app's"),
        ("verifactu.record.list", "a query"),
        ("verifactu.record.create", "needs an input"),
    ],
    ids=["unknown", "another-app", "query", "needs-input"],
)
def test_the_operation_is_a_command_of_the_same_app_that_runs_without_input(
    operation, why
):
    [(code, message)] = errors_of(entry(operation=operation))

    assert code == "base.E003", why
    assert operation in message


@pytest.mark.parametrize(
    "bad",
    [
        entry(catch_up="skip"),
        {"name": "process_queue", "operation": "verifactu.contingency.process"},
        entry(extra=True),
        entry(name="Process Queue"),
        "verifactu.contingency.process",
    ],
    ids=["catch-up", "missing-cron", "unknown-key", "name", "not-a-dict"],
)
def test_a_task_out_of_shape_is_refused(bad):
    assert [code for code, _ in errors_of(bad)] == ["base.E001"]


def test_two_tasks_of_an_app_never_share_a_name():
    assert [code for code, _ in errors_of(entry(), entry(cron="0 * * * *"))] == [
        "base.E001"
    ]


# ── The cron, in UTC ───────────────────────────────────────────────────────────────────────────


def test_the_next_time_is_strictly_after_now():
    assert scheduler.next_after("* * * * *", at(10, 0)) == at(10, 1)
    assert scheduler.next_after("*/5 * * * *", at(10, 2, 30)) == at(10, 5)


def test_a_module_task_stays_on_utc_whatever_zone_the_clock_is_in():
    # A programmer writes the cron months before anybody knows where the hub is: it means UTC.
    # 10:30 in Madrid is 08:30 UTC: 09:00 UTC comes today (read in Madrid's time it would be tomorrow).
    madrid = dt.datetime(
        2026, 10, 15, 10, 30, tzinfo=zoneinfo.ZoneInfo("Europe/Madrid")
    )

    assert scheduler.next_after("0 9 * * *", madrid) == at(9, 0)


# ── The schedule in the database ───────────────────────────────────────────────────────────────


def next_run(name: str, app: str = "test") -> dt.datetime:
    return TaskSchedule.objects.get(app_label=app, name=name).next_run


@pytest.mark.django_db
def test_sync_schedules_a_new_task_at_its_next_time_and_keeps_the_clock_of_a_known_one():
    scheduler.sync(at(9, 59, 30), declared=[task("tick")])
    assert next_run("tick") == at(10, 0)

    # As if it had been running for a while: a later boot never resets its clock.
    TaskSchedule.objects.update(next_run=at(23, 0))
    scheduler.sync(at(10, 30), declared=[task("tick", cron="0 * * * *")])

    row = TaskSchedule.objects.get()
    assert (row.cron, row.next_run, row.operation) == (
        "0 * * * *",
        at(23, 0),
        "test.task.tick",
    )


@pytest.mark.django_db
def test_sync_forgets_a_task_no_app_declares_any_more():
    scheduler.sync(at(10, 0), declared=[task("tick"), task("gone")])
    scheduler.sync(at(10, 0), declared=[task("tick")])

    assert list(TaskSchedule.objects.values_list("name", flat=True)) == ["tick"]


@pytest.mark.django_db
def test_sync_without_declarations_reads_the_apps():
    scheduler.sync(at(10, 0))

    assert set(TaskSchedule.objects.values_list("app_label", "name")) == {
        (t.app_label, t.name) for t in scheduler.tasks()
    }


# ── Running what is due ────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_task_runs_on_its_minute_and_not_before(ticks):
    scheduler.sync(at(9, 59, 30), declared=[task("tick")])

    assert scheduler.run_due(at(10, 0)) == ["test.tick"]
    assert scheduler.run_due(at(10, 0, 30)) == []
    assert scheduler.run_due(at(10, 1)) == ["test.tick"]
    assert len(ticks) == 2
    row = TaskSchedule.objects.get()
    assert (row.last_run, row.next_run) == (at(10, 1), at(10, 2))


@pytest.mark.django_db
def test_minutes_missed_while_stopped_collapse_into_one_run(ticks):
    scheduler.sync(at(9, 59, 30), declared=[task("tick")])
    scheduler.run_due(at(10, 0))

    # Five minutes stopped: one run, then the next time after now.
    assert scheduler.run_due(at(10, 6)) == ["test.tick"]
    assert scheduler.run_due(at(10, 6)) == []
    assert len(ticks) == 2
    assert next_run("tick") == at(10, 7)


@pytest.mark.django_db
def test_a_task_runs_as_the_system_on_the_workers_scope(settings, ticks):
    settings.WORKER_SCOPE_SLUG = "acme"
    scheduler.sync(at(9, 59), declared=[task("tick")])

    scheduler.run_due(at(10, 0))

    [(ctx, data)] = ticks
    assert (ctx.scope, ctx.actor, ctx.permissions) == (
        Scope("host", "acme"),
        "system",
        frozenset({"*"}),
    )
    assert isinstance(data, NoIn)


@pytest.mark.django_db
def test_a_task_that_raises_is_logged_rolled_back_and_the_others_still_run(
    monkeypatch, caplog, ticks
):
    def boom(ctx, data):
        get_user_model().objects.create_user("half-done")
        raise RuntimeError("broken task")

    fake_operation(monkeypatch, "test.task.boom", boom)
    scheduler.sync(at(9, 59), declared=[task("boom"), task("tick")])

    with caplog.at_level(logging.ERROR, logger="base.services"):
        assert scheduler.run_due(at(10, 0)) == ["test.tick"]

    assert len(ticks) == 1
    assert not get_user_model().objects.filter(username="half-done").exists()
    [record] = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "test.boom" in record.getMessage()
    assert str(record.exc_info[1]) == "broken task"
    # Rescheduled, not retried on every tick; it never finished, so it has no last run.
    boom = TaskSchedule.objects.get(name="boom")
    assert (boom.next_run, boom.last_run) == (at(10, 1), None)
    assert scheduler.run_due(at(10, 0, 30)) == []


@pytest.mark.django_db
def test_a_task_whose_operation_is_gone_is_logged_and_rescheduled(caplog):
    scheduler.sync(at(9, 59), declared=[task("vanished")])

    with caplog.at_level(logging.ERROR, logger="base.services"):
        assert scheduler.run_due(at(10, 0)) == []

    assert "test.vanished" in caplog.text
    assert next_run("vanished") == at(10, 1)


@pytest.mark.django_db(transaction=True)
def test_two_workers_never_run_the_same_due_task(monkeypatch):
    # The deploy starts the new worker before stopping the old one: both tick on the same row.
    monkeypatch.setattr(scheduler, "close_old_connections", close_old_connections)
    seen_by_the_other: list[list[str]] = []
    runs: list[bool] = []

    def slow(ctx, data):
        def other_worker():
            try:
                seen_by_the_other.append(scheduler.run_due(at(10, 0)))
            finally:
                connection.close()

        runs.append(True)
        if len(runs) == 1:
            # While this run holds the row, the other worker ticks; it must neither run it nor wait.
            thread = threading.Thread(target=other_worker)
            thread.start()
            thread.join(timeout=10)
            runs.append(thread.is_alive())
        return Done()

    fake_operation(monkeypatch, "test.task.slow", slow)
    scheduler.sync(at(9, 59), declared=[task("slow")])

    assert scheduler.run_due(at(10, 0)) == ["test.slow"]
    # The other worker skipped the row this one held, and once it committed the row was not due.
    assert runs == [True, False]
    assert seen_by_the_other == [[]]
    assert scheduler.run_due(at(10, 0)) == []
    assert next_run("slow") == at(10, 1)


@pytest.mark.django_db
def test_the_connections_are_released_after_every_task_and_before_idling(released, ticks):
    scheduler.sync(at(9, 59), declared=[task("tick")])

    scheduler.run_due(at(10, 0))
    # One task, then the claim that found nothing: the worker never idles holding a connection.
    assert released == ["close", "close"]

    scheduler.run_due(at(10, 0, 30))
    assert released == ["close"] * 3


def test_the_check_runs_with_every_system_check():
    # In a fresh process, where nothing imported the scheduler before Django was set up.
    probe = (
        "import django; django.setup(); from django.core.checks.registry import registry; "
        "print(sorted(c.__module__ for c in registry.get_checks() if c.__module__.startswith('base.')))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=settings.BASE_DIR,
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert "base.scheduler" in done.stdout
