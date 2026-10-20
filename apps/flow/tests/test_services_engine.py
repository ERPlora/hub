"""The engine (WORKBOOK FLOW-F21 to F23): what starts a run, how its steps run, what a failure leaves,
waits, schedules, one run per event and the guard against chains that never end.

Events are handed over as the relay will (``events.react``); the clock is frozen (``clock``); the
actions are the real ones of Tasks and Customers.
"""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest
from live.models import OutboxEvent
from live.operations import get

from apps.customer.models import Customer
from apps.flow import events
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task

from .conftest import A, TASK_STEP, make_flow, make_run, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CREATED = "customer.customer.created"


def deliver(
    name: str = CREATED,
    payload: dict | None = None,
    *,
    event_id=None,
    actor: str = "system",
):
    return events.react(
        A, name, payload or {}, event_id=event_id or uuid.uuid7(), actor=actor
    )


def flow_events() -> list[str]:
    return [
        e.name
        for e in OutboxEvent.objects.order_by("created_at", "id")
        if e.name.startswith("flow.")
    ]


# What starts a run


def test_an_event_starts_the_flows_that_wait_for_it_and_only_those(clock):
    clock(NOON)
    waiting = make_flow("Waits for it")
    make_flow("Paused", enabled=False)
    make_flow("Other event", trigger_event="sale.sale.completed")
    make_flow("By hand", trigger_kind=Flow.Trigger.MANUAL)
    from django.utils import timezone

    make_flow("Gone", deleted_at=timezone.now())
    result = deliver(payload={"id": "c-1"})
    assert (result.started, result.skipped) == (1, 0)
    created = FlowRun.objects.get()
    assert (created.flow, created.status, created.input, created.event_name) == (
        waiting,
        FlowRun.Status.SUCCEEDED,
        {"id": "c-1"},
        CREATED,
    )
    assert (created.started_at, created.finished_at, created.started_by) == (
        NOON,
        NOON,
        "system",
    )
    assert created.log == [
        {
            "step": "s1",
            "kind": "command",
            "operation": "task.task.create",
            "outcome": "done",
            "at": NOON.isoformat(),
        }
    ]
    assert Task.objects.get().title == "Welcome the new customer"
    assert flow_events() == ["flow.run.started", "flow.run.finished"]


def test_only_when_its_filter_holds():
    make_flow(
        trigger_filter={"input.total": {"gte": 10000}},
        trigger_event="sale.sale.completed",
    )
    assert deliver("sale.sale.completed", {"total": 500}).skipped == 1
    assert deliver("sale.sale.completed", {"total": 15000}).started == 1
    assert FlowRun.objects.count() == 1


def test_the_same_event_twice_runs_once():
    make_flow()
    event_id = uuid.uuid7()
    assert deliver(event_id=event_id).started == 1
    assert (deliver(event_id=event_id).started, deliver(event_id=event_id).skipped) == (
        0,
        1,
    )
    assert (FlowRun.objects.count(), Task.objects.count()) == (1, 1)


def test_its_own_events_start_nothing():
    make_flow(trigger_event="task.task.created")
    assert events.react(A, "flow.run.finished", {}, event_id=uuid.uuid7()) is None


# How the steps run


def test_a_step_reads_the_event_and_what_earlier_steps_left():
    make_flow(
        steps=[
            {
                "id": "s1",
                "kind": "query",
                "operation": "customer.customer.detail",
                "params": {"id": "input.id"},
            },
            {"id": "s2", "kind": "condition", "when": {"steps.s1.found": {"eq": True}}},
            TASK_STEP
            | {
                "id": "s3",
                "params": {"title": "Call {{steps.s1.name}}", "priority": "high"},
            },
            TASK_STEP
            | {
                "id": "s4",
                "params": {
                    "title": "After {{steps.s3.number}}",
                    "parent_id": "steps.s3.id",
                },
            },
        ],
        grants=["customer.customer.detail", "task.task.create"],
    )
    customer = Customer.objects.create(name="Ana López")
    deliver(payload={"id": str(customer.id)})
    run_ = FlowRun.objects.get()
    assert run_.status == FlowRun.Status.SUCCEEDED, run_.log
    first, second = Task.objects.order_by("created_at")
    assert (first.title, first.priority) == ("Call Ana López", "high")
    assert (second.title, second.parent_id) == (f"After {first.number}", first.id)
    assert run_.log[0]["count"] == 1
    assert [entry["outcome"] for entry in run_.log] == [
        "found",
        "passed",
        "done",
        "done",
    ]


def test_a_read_that_finds_nothing_carries_on():
    make_flow(
        steps=[
            {
                "id": "s1",
                "kind": "query",
                "operation": "customer.customer.detail",
                "params": {"id": "input.id"},
            },
            {
                "id": "s2",
                "kind": "condition",
                "when": {"steps.s1.found": {"eq": False}},
            },
            TASK_STEP | {"id": "s3", "params": {"title": "Nobody"}},
        ],
        grants=["customer.customer.detail", "task.task.create"],
    )
    deliver(payload={"id": str(uuid.uuid7())})
    run_ = FlowRun.objects.get()
    assert run_.status == FlowRun.Status.SUCCEEDED
    assert run_.log[0]["count"] == 0
    assert run_.log[0]["outcome"] == "not_found"
    assert Task.objects.get().title == "Nobody"


def test_a_read_that_counts_keeps_only_how_many():
    for name in ("Ana", "Luis", "Eva"):
        Customer.objects.create(name=name)
    make_flow(
        steps=[
            {
                "id": "s1",
                "kind": "query",
                "operation": "customer.customer.list",
                "params": {},
                "result": "count",
            },
            TASK_STEP
            | {"id": "s2", "params": {"title": "There are {{steps.s1.count}}"}},
        ],
        grants=["customer.customer.list", "task.task.create"],
    )
    deliver()
    assert FlowRun.objects.get().log[0]["count"] == 3
    assert Task.objects.get().title == "There are 3"


def test_a_condition_that_does_not_hold_ends_the_run_without_error():
    make_flow(
        steps=[
            {"id": "s1", "kind": "condition", "when": {"input.vip": {"eq": True}}},
            TASK_STEP | {"id": "s2"},
        ],
    )
    deliver(payload={"vip": False})
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.error_code) == (FlowRun.Status.STOPPED, "")
    assert run_.log[0]["outcome"] == "stopped"
    assert run_.log[0]["failed"] == [{"path": "input.vip", "op": "eq", "value": True}]
    assert Task.objects.count() == 0


# What a failure leaves


def test_a_step_it_was_not_allowed_stops_the_run_and_says_why():
    make_flow(grants=[])
    deliver()
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.error_code) == (FlowRun.Status.FAILED, "flow.not_allowed")
    assert run_.error_message == (
        "It tried to do something you have not allowed it to do («task.task.create»), so it stopped. "
        "Open Permissions and allow what it needs."
    )
    assert run_.log[0]["outcome"] == "failed"
    assert Task.objects.count() == 0


def test_the_messages_are_in_the_language_of_who_saved_it():
    make_flow(grants=[], language="es")
    deliver()
    assert FlowRun.objects.get().error_message.startswith(
        "Ha intentado hacer algo que no le has permitido"
    )


def test_what_the_action_refuses_stops_the_run_and_earlier_steps_stay():
    make_flow(
        steps=[
            TASK_STEP,
            TASK_STEP | {"id": "s2", "params": {"title": "x", "priority": "soon"}},
        ],
    )
    deliver()
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.error_code, run_.step_index) == (
        FlowRun.Status.FAILED,
        "flow.invalid_params",
        1,
    )
    assert run_.log[1]["error"]["fields"] == {
        "priority": "Input should be 'low', 'medium', 'high' or 'urgent'"
    }
    assert Task.objects.count() == 1


def test_an_action_that_says_no_stops_the_run_with_its_own_words():
    make_flow(
        steps=[TASK_STEP | {"params": {"title": "x", "project": "No such project"}}],
    )
    deliver()
    run_ = FlowRun.objects.get()
    assert run_.status == FlowRun.Status.FAILED
    assert run_.error_code == "invalid_field"
    assert "project" in run_.log[0]["error"]["fields"]


def test_an_action_whose_app_is_gone_is_unavailable(monkeypatch):
    from apps.flow import queries

    make_flow()
    active = {
        label: config
        for label, config in queries.active_apps().items()
        if label != "task"
    }
    monkeypatch.setattr(queries, "active_apps", lambda: active)
    deliver()
    assert FlowRun.objects.get().error_code == "flow.action_unavailable"


def test_an_unexpected_failure_of_a_step_is_kept_and_visible(monkeypatch, caplog):
    make_flow(steps=[TASK_STEP, TASK_STEP | {"id": "s2"}])
    op = get("task.task.create")
    calls = {"n": 0}
    real = op.fn

    def second_breaks(ctx, data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk on fire")
        return real(ctx, data)

    monkeypatch.setattr(op, "fn", second_breaks)
    deliver()
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.error_code) == (
        FlowRun.Status.FAILED,
        "flow.step_crashed",
    )
    assert run_.log[1]["error"]["technical"] == "RuntimeError: disk on fire"
    assert Task.objects.count() == 1
    assert "disk on fire" in caplog.text


# Waits (FLOW-F23)


def test_a_wait_parks_the_run_and_the_scheduled_task_resumes_it(clock):
    clock(NOON)
    flow = make_flow(
        steps=[{"id": "s1", "kind": "delay", "seconds": 3600}, TASK_STEP | {"id": "s2"}]
    )
    deliver()
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.resume_at, run_.step_index) == (
        FlowRun.Status.WAITING,
        NOON + dt.timedelta(hours=1),
        1,
    )
    assert run_.log[0] == {
        "step": "s1",
        "kind": "delay",
        "outcome": "waiting",
        "seconds": 3600,
        "until": (NOON + dt.timedelta(hours=1)).isoformat(),
        "at": NOON.isoformat(),
    }
    clock(NOON + dt.timedelta(minutes=59))
    assert run("flow.run.resume_due", {}, _system()).count == 0
    # The automation changes meanwhile: the run goes on with the steps it started with.
    Flow.objects.filter(pk=flow.pk).update(steps=[], version=2)
    clock(NOON + dt.timedelta(hours=1))
    assert run("flow.run.resume_due", {}, _system()).count == 1
    run_.refresh_from_db()
    assert run_.status == FlowRun.Status.SUCCEEDED
    assert run_.log[0]["outcome"] == "waited"
    assert Task.objects.count() == 1
    assert flow_events() == [
        "flow.run.started",
        "flow.run.parked",
        "flow.run.resumed",
        "flow.run.finished",
    ]


def test_a_wait_of_a_paused_automation_is_cancelled_when_it_wakes(clock):
    clock(NOON)
    flow = make_flow(
        steps=[{"id": "s1", "kind": "delay", "seconds": 60}, TASK_STEP | {"id": "s2"}]
    )
    deliver()
    Flow.objects.filter(pk=flow.pk).update(enabled=False)
    clock(NOON + dt.timedelta(minutes=2))
    run("flow.run.resume_due", {}, _system())
    run_ = FlowRun.objects.get()
    assert (run_.status, run_.error_code) == (FlowRun.Status.CANCELLED, "flow.paused")
    assert Task.objects.count() == 0


def test_turned_on_again_before_it_wakes_it_goes_on(clock):
    clock(NOON)
    flow = make_flow(
        steps=[{"id": "s1", "kind": "delay", "seconds": 60}, TASK_STEP | {"id": "s2"}]
    )
    deliver()
    run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": False}, _admin())
    run("flow.flow.set_enabled", {"id": str(flow.id), "enabled": True}, _admin())
    clock(NOON + dt.timedelta(minutes=2))
    run("flow.run.resume_due", {}, _system())
    assert FlowRun.objects.get().status == FlowRun.Status.SUCCEEDED


# Schedules and dates (FLOW-F22)


def test_a_schedule_starts_once_when_its_time_comes_even_after_missing_several(clock):
    flow = make_flow(
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
        next_fire_at=dt.datetime(2026, 10, 13, 9, 0, tzinfo=MADRID),
    )
    clock(dt.datetime(2026, 10, 13, 8, 59, tzinfo=MADRID))
    assert run("flow.schedule.fire_due", {}, _system()).count == 0
    clock(NOON)
    assert run("flow.schedule.fire_due", {}, _system()).count == 1
    started = FlowRun.objects.get()
    assert (started.trigger_kind, started.trigger_key) == (
        "schedule",
        "schedule:2026-10-13T09:00:00+02:00",
    )
    flow.refresh_from_db()
    assert flow.next_fire_at == dt.datetime(2026, 10, 16, 9, 0, tzinfo=MADRID)
    assert run("flow.schedule.fire_due", {}, _system()).count == 0
    assert Task.objects.count() == 1


def test_a_date_starts_once_and_never_again(clock):
    when = dt.datetime(2026, 10, 20, 10, 0, tzinfo=MADRID)
    flow = make_flow(
        trigger_kind=Flow.Trigger.AT, trigger_event="", run_at=when, next_fire_at=when
    )
    clock(when + dt.timedelta(seconds=30))
    assert run("flow.schedule.fire_due", {}, _system()).count == 1
    flow.refresh_from_db()
    assert flow.next_fire_at is None
    assert run("flow.schedule.fire_due", {}, _system()).count == 0


def test_a_paused_or_deleted_schedule_does_not_start(clock):
    from django.utils import timezone

    due = dt.datetime(2026, 10, 15, 9, 0, tzinfo=MADRID)
    common = {
        "trigger_kind": Flow.Trigger.SCHEDULE,
        "trigger_event": "",
        "schedule": {"every": "day", "time": "09:00"},
    }
    make_flow("Paused", enabled=False, next_fire_at=due, **common)
    make_flow("Gone", deleted_at=timezone.now(), next_fire_at=due, **common)
    clock(NOON)
    assert run("flow.schedule.fire_due", {}, _system()).count == 0


# Chains that never end


def test_an_automation_started_by_its_own_steps_stops_before_doing_anything():
    flow = make_flow(trigger_event="task.task.created")
    parent = make_run(flow)
    deliver("task.task.created", {"id": "t"}, actor=f"flow_run:{parent.id}")
    looped = FlowRun.objects.exclude(pk=parent.pk).get()
    assert (looped.status, looped.error_code) == (
        FlowRun.Status.FAILED,
        "flow.loop_stopped",
    )
    assert looped.chain == [str(flow.id)]
    assert looped.log == []
    assert Task.objects.count() == 0


def test_a_chain_of_other_automations_goes_on_up_to_its_limit():
    first = make_flow("First", trigger_event="task.task.created")
    other = make_flow("Other", trigger_event="task.task.created", steps=[], grants=[])
    parent = make_run(other, chain=[str(uuid.uuid7()) for _ in range(6)])
    deliver("task.task.created", {"id": "t"}, actor=f"flow_run:{parent.id}")
    child = FlowRun.objects.get(flow=first)
    assert child.status == FlowRun.Status.SUCCEEDED
    assert len(child.chain) == 7
    too_deep = make_run(other, chain=[str(uuid.uuid7()) for _ in range(7)])
    deliver("task.task.created", {"id": "t2"}, actor=f"flow_run:{too_deep.id}")
    stopped = FlowRun.objects.filter(flow=first).exclude(pk=child.pk).get()
    assert (stopped.status, stopped.error_code) == (
        FlowRun.Status.FAILED,
        "flow.loop_stopped",
    )


def test_what_a_run_does_carries_its_reference():
    make_flow()
    deliver()
    run_ = FlowRun.objects.get()
    created = OutboxEvent.objects.get(name="task.task.created")
    assert created.actor == f"flow_run:{run_.id}"


def _system():
    from live.context import system_context

    return system_context(A)


def _admin():
    from .conftest import ctx_for

    return ctx_for()


def test_a_finished_run_keeps_no_copy_of_what_its_steps_read(clock):
    # Review 2026-10-15, item 6: a read leaves a customer's card in the run; only a waiting run needs it.
    clock(NOON)
    make_flow(
        steps=[
            {"id": "s1", "kind": "query", "operation": "customer.customer.detail", "params": {"id": "input.id"}},
            {"id": "s2", "kind": "delay", "seconds": 60},
            TASK_STEP | {"id": "s3", "params": {"title": "Call {{steps.s1.name}}"}},
        ],
        grants=["customer.customer.detail", "task.task.create"],
    )
    customer = Customer.objects.create(name="Ana López")
    deliver(payload={"id": str(customer.id)})
    waiting = FlowRun.objects.get()
    assert waiting.outputs["s1"]["name"] == "Ana López"
    clock(NOON + dt.timedelta(minutes=2))
    run("flow.run.resume_due", {}, _system())
    waiting.refresh_from_db()
    assert (waiting.status, waiting.outputs) == (FlowRun.Status.SUCCEEDED, {})
    assert Task.objects.get().title == "Call Ana López"


# The phase-1 worker (FLOW-F22, FLOW-F23): `run_worker` calls `base.scheduler.run_due` every tick, on
# one fixed scope; these tests go through that same scheduler, with the tasks flow declares.


def _flow_tasks():
    from base import scheduler

    return [task for task in scheduler.tasks() if task.app_label == "flow"]


def test_the_workers_tick_fires_a_due_schedule_and_resumes_a_wait(clock, settings, monkeypatch):
    from base import scheduler

    # The worker releases its connection after each task; the test's transaction must stay open.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    settings.WORKER_SCOPE_SLUG = "a"
    clock(NOON - dt.timedelta(minutes=1))
    scheduler.sync(NOON - dt.timedelta(minutes=1), declared=_flow_tasks())
    daily = make_flow(
        "Every day at noon",
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "12:00"},
        next_fire_at=NOON,
    )
    waits = make_flow(
        "Wait two minutes",
        steps=[{"id": "s1", "kind": "delay", "seconds": 120}, TASK_STEP | {"id": "s2"}],
    )
    deliver()
    assert FlowRun.objects.get(flow=waits).status == FlowRun.Status.WAITING

    clock(NOON)
    assert sorted(scheduler.run_due(NOON)) == ["flow.fire_due", "flow.resume_due"]
    fired = FlowRun.objects.get(flow=daily)
    assert (fired.trigger_kind, fired.status) == ("schedule", FlowRun.Status.SUCCEEDED)
    assert FlowRun.objects.get(flow=waits).status == FlowRun.Status.WAITING

    clock(NOON + dt.timedelta(minutes=1))
    assert sorted(scheduler.run_due(NOON + dt.timedelta(minutes=1))) == [
        "flow.fire_due",
        "flow.resume_due",
    ]
    assert FlowRun.objects.get(flow=waits).status == FlowRun.Status.SUCCEEDED
    assert FlowRun.objects.filter(flow=daily).count() == 1
    assert Task.objects.count() == 2


def test_a_tick_with_nothing_due_records_and_announces_nothing(clock):
    # hub#2612: a scheduled task that finds nothing to do leaves no event, so no live list re-runs.
    flow = make_flow(
        trigger_kind=Flow.Trigger.SCHEDULE,
        trigger_event="",
        schedule={"every": "day", "time": "09:00"},
        next_fire_at=dt.datetime(2026, 10, 16, 9, 0, tzinfo=MADRID),
    )
    make_run(flow, status=FlowRun.Status.WAITING, resume_at=NOON + dt.timedelta(hours=1))
    clock(NOON)
    before = OutboxEvent.objects.count()
    assert run("flow.schedule.fire_due", {}, _system()).count == 0
    assert run("flow.run.resume_due", {}, _system()).count == 0
    assert OutboxEvent.objects.count() == before


# A document the engine can no longer read (hub#1766: written raw from the admin, or by an older
# version): it fails visibly in its own history, and the other automations still run.


def test_a_filter_it_cannot_read_fails_its_run_visibly_and_the_others_still_start(clock):
    clock(NOON)
    fine = make_flow("Fine")
    broken = make_flow("Broken", trigger_filter={"input.total": {"bigger": 10}})
    assert deliver().started == 2
    failed = FlowRun.objects.get(flow=broken)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.filter_unreadable")
    assert "«Only when…»" in failed.error_message
    assert FlowRun.objects.get(flow=fine).status == FlowRun.Status.SUCCEEDED
    assert Task.objects.count() == 1


def test_a_condition_it_cannot_read_stops_the_run_with_its_reason(clock):
    clock(NOON)
    make_flow(
        steps=[
            {"id": "s1", "kind": "condition", "when": {"input.total": {"bigger": 10}}},
            TASK_STEP | {"id": "s2"},
        ]
    )
    deliver(payload={"total": 20})
    failed = FlowRun.objects.get()
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.condition_unreadable")
    assert failed.log[-1]["outcome"] == "failed"
    assert failed.log[-1]["error"]["code"] == "flow.condition_unreadable"
    assert Task.objects.count() == 0
