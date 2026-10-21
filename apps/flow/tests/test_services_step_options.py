"""«Only if…» and «if it fails, carry on» on each step (WORKBOOK FLOW-F25; old hub HUB-F97).

Any step but «Only continue if…» may carry ``run_if``: when it does not hold the step is skipped, says so
in the history and the run goes on (later steps read ``steps.<id>.skipped``). An action or a read may
carry ``on_error: continue``: its failure is written in the step, the run goes on and later steps read
``steps.<id>.failed``. Without saying anything, a step that fails stops the run, as before. The actions
are the real ones of Tasks and Customers.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pydantic
import pytest

from apps.customer.models import Customer
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task

from .conftest import TASK_STEP, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
DENIED = {"id": "s1", "kind": "command", "operation": "customer.customer.create", "params": {"name": "Ana"}}


def _manual(steps, grants=("task.task.create",)):
    return make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=list(grants))


def _run_now(flow, data=None):
    return run("flow.flow.run", {"id": str(flow.id), "input": data or {}})


def test_a_step_whose_only_if_does_not_hold_is_skipped_and_the_run_goes_on(clock):
    clock(NOON)
    flow = _manual(
        [
            TASK_STEP | {"run_if": {"input.total": {"gt": 10000}}},
            TASK_STEP | {"id": "s2", "params": {"title": "Always"}},
        ]
    )
    ran = _run_now(flow, {"total": 500})
    assert ran.status == "succeeded"
    assert list(Task.objects.values_list("title", flat=True)) == ["Always"]
    assert [entry["outcome"] for entry in ran.log] == ["skipped", "done"]
    assert ran.log[0]["failed"] == [{"path": "input.total", "op": "gt", "value": 10000}]


def test_a_step_whose_only_if_holds_runs(clock):
    clock(NOON)
    flow = _manual([TASK_STEP | {"run_if": {"input.total": {"gt": 10000}}}])
    ran = _run_now(flow, {"total": 20000})
    assert [entry["outcome"] for entry in ran.log] == ["done"]
    assert Task.objects.count() == 1


def test_later_steps_read_that_a_step_was_skipped(clock):
    clock(NOON)
    flow = _manual(
        [
            TASK_STEP | {"run_if": {"input.vip": {"eq": True}}},
            TASK_STEP | {"id": "s2", "params": {"title": "Only when s1 was skipped"}, "run_if": {"steps.s1.skipped": {"eq": True}}},
        ]
    )
    _run_now(flow, {"vip": False})
    assert list(Task.objects.values_list("title", flat=True)) == ["Only when s1 was skipped"]


def test_a_wait_can_be_skipped_too(clock):
    clock(NOON)
    flow = _manual([{"id": "s1", "kind": "delay", "seconds": 3600, "run_if": {"input.later": {"eq": True}}}, dict(TASK_STEP, id="s2")])
    ran = _run_now(flow, {"later": False})
    assert (ran.status, [entry["outcome"] for entry in ran.log]) == ("succeeded", ["skipped", "done"])


def test_a_failing_step_that_carries_on_writes_its_failure_and_the_run_goes_on(clock):
    clock(NOON)
    flow = _manual(
        [
            DENIED | {"on_error": "continue"},
            TASK_STEP | {"id": "s2", "params": {"title": "Failed: {{steps.s1.error_code}}"}, "run_if": {"steps.s1.failed": {"eq": True}}},
        ]
    )
    ran = _run_now(flow)
    assert (ran.status, ran.error_code) == ("succeeded", "")
    assert Customer.objects.count() == 0
    assert list(Task.objects.values_list("title", flat=True)) == ["Failed: flow.not_allowed"]
    assert ran.log[0]["outcome"] == "failed" and ran.log[0]["continued"] is True
    assert ran.log[0]["error"]["code"] == "flow.not_allowed"


def test_without_saying_anything_a_failing_step_stops_the_run(clock):
    clock(NOON)
    flow = _manual([DENIED, TASK_STEP | {"id": "s2"}])
    ran = _run_now(flow)
    assert (ran.status, ran.error_code) == ("failed", "flow.not_allowed")
    assert Task.objects.count() == 0


def test_an_only_if_it_cannot_read_stops_the_run_visibly(clock):
    clock(NOON)
    flow = _manual([TASK_STEP | {"run_if": {"input.total": {"bigger": 1}}}])
    ran = _run_now(flow)
    assert (ran.status, ran.error_code) == ("failed", "flow.run_if_unreadable")
    assert Task.objects.count() == 0
    assert run("flow.run.list", {"flow_id": str(flow.id)}).rows[0].resumable is False


def test_saving_checks_the_only_if_and_the_on_error(clock):
    clock(NOON)
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [TASK_STEP | {"run_if": {"input.total": {"bigger": 1}}}]})
    with pytest.raises(pydantic.ValidationError):
        run("flow.flow.create", {"steps": [TASK_STEP | {"on_error": "retry"}]})
    with pytest.raises(pydantic.ValidationError):  # a wait cannot fail: nothing to carry on from
        run("flow.flow.create", {"steps": [{"id": "s1", "kind": "delay", "seconds": 60, "on_error": "continue"}]})
    with pytest.raises(pydantic.ValidationError):  # «Only continue if…» is a condition already
        run("flow.flow.create", {"steps": [{"id": "s1", "kind": "condition", "when": {"input.a": {"eq": 1}}, "run_if": {"input.b": {"eq": 1}}}]})
    with pytest.raises(pydantic.ValidationError) as later:  # an «Only if…» reads only what earlier steps leave
        run("flow.flow.create", {"steps": [TASK_STEP | {"run_if": {"steps.s2.found": {"eq": True}}}, TASK_STEP | {"id": "s2"}]})
    assert "steps.s2.found" in str(later.value)


def test_a_step_without_options_is_saved_as_it_was():
    created = run("flow.flow.create", {"steps": [dict(TASK_STEP)]})
    assert created.steps == [TASK_STEP]
    with_options = run(
        "flow.flow.create",
        {"steps": [TASK_STEP | {"run_if": {"input.total": {"gt": 1}}, "on_error": "continue"}]},
    )
    assert with_options.steps == [TASK_STEP | {"run_if": {"input.total": {"gt": 1}}, "on_error": "continue"}]


def test_try_it_says_a_step_would_be_skipped(clock):
    clock(NOON)
    flow = _manual([TASK_STEP | {"run_if": {"input.total": {"gt": 10000}}}])
    import json

    tried = run(
        "flow.flow.test",
        {"id": str(flow.id), "document": json.dumps({"trigger": {"kind": "manual"}, "steps": flow.steps})},
    )
    assert tried.steps[0].outcome == "skipped"
    assert [clause.model_dump() for clause in tried.steps[0].failed] == [{"path": "input.total", "op": "gt", "value": 10000}]


def test_a_skipped_step_of_a_failed_run_does_not_prevent_resuming_it(clock):
    clock(NOON)
    flow = _manual([TASK_STEP | {"run_if": {"input.go": {"eq": True}}}, DENIED | {"id": "s2"}])
    ran = _run_now(flow)
    assert (ran.status, ran.resumable) == ("failed", True)
    assert FlowRun.objects.get().outputs == {"s1": {"skipped": True}}
