"""Resume a run from the step that failed (WORKBOOK FLOW-F24; old hub HUB-F103, hub#952).

A run that stopped by an error keeps what its steps left for seven days; within them, once the cause is
fixed, ``flow.run.retry`` takes it up again at the step that failed, without repeating the steps that
already had an effect, with the version of the automation it started with. The actions are the real
ones of Customers.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.customer.models import Activity, Customer
from apps.flow import queries
from apps.flow.models import FlowRun

from .conftest import ctx_for, make_flow, make_run, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CREATE_STEP = {
    "id": "s1",
    "kind": "command",
    "operation": "customer.customer.create",
    "params": {"name": "Ana López"},
}
NOTE_STEP = {
    "id": "s2",
    "kind": "command",
    "operation": "customer.note.add",
    "params": {"customer_id": "steps.s1.id", "content": "Call them back"},
}
BOTH = ["customer.customer.create", "customer.note.add"]


def notes() -> int:
    return Activity.objects.filter(text="Call them back").count()


def _failed_at_the_second_step(clock) -> FlowRun:
    """A manual run that created a customer (s1) and stopped at s2, which was not allowed yet."""
    clock(NOON)
    flow = make_flow(
        trigger_kind="manual",
        steps=[dict(CREATE_STEP), dict(NOTE_STEP)],
        grants=["customer.customer.create"],
    )
    run("flow.flow.run", {"id": str(flow.id)})
    failed = FlowRun.objects.get()
    assert (failed.status, failed.error_code, failed.step_index) == (
        FlowRun.Status.FAILED,
        "flow.not_allowed",
        1,
    )
    return failed


def test_a_failed_run_resumes_at_the_step_that_failed_and_does_not_repeat_the_ones_before(clock):
    failed = _failed_at_the_second_step(clock)
    flow = failed.flow
    flow.grants = BOTH
    flow.save()
    clock(NOON + dt.timedelta(hours=1))
    resumed = run("flow.run.retry", {"id": str(failed.id)})
    assert (resumed.status, resumed.error_code, resumed.error_message) == ("succeeded", "", "")
    customer = Customer.objects.get()  # the first step did not run again
    assert Activity.objects.get(text="Call them back").customer_id == customer.id  # read what s1 left
    failed.refresh_from_db()
    assert failed.finished_at == NOON + dt.timedelta(hours=1)
    assert [entry["outcome"] for entry in failed.log] == ["done", "failed", "resumed", "done"]
    assert failed.log[2]["step"] == "s2" and failed.log[2]["by"] == "tester"
    assert failed.outputs == {}  # finished well: nothing it read is kept
    names = [event.name for event in OutboxEvent.objects.order_by("created_at", "id")]
    assert names[-3:] == ["flow.run.resumed", "customer.note.added", "flow.run.finished"]


def test_a_failed_run_keeps_what_its_steps_left_so_that_it_can_resume(clock):
    failed = _failed_at_the_second_step(clock)
    assert set(failed.outputs) == {"s1"}
    assert run("flow.run.list", {"flow_id": str(failed.flow_id)}).rows[0].resumable is True


def test_it_resumes_with_the_steps_it_started_with_even_if_the_automation_changed(clock):
    failed = _failed_at_the_second_step(clock)
    flow = failed.flow
    flow.steps = [dict(CREATE_STEP, params={"name": "Somebody else"})]
    flow.version += 1
    flow.grants = BOTH
    flow.save()
    run("flow.run.retry", {"id": str(failed.id)})
    assert notes() == 1
    assert Customer.objects.get().name == "Ana López"


def test_a_step_that_fails_again_leaves_the_run_failed_and_resumable_again(clock):
    failed = _failed_at_the_second_step(clock)
    resumed = run("flow.run.retry", {"id": str(failed.id)})
    assert (resumed.status, resumed.error_code, resumed.resumable) == ("failed", "flow.not_allowed", True)
    assert [entry["outcome"] for entry in resumed.log] == ["done", "failed", "resumed", "failed"]


def test_only_a_run_stopped_by_an_error_resumes_and_only_once(clock):
    failed = _failed_at_the_second_step(clock)
    failed.flow.grants = BOTH
    failed.flow.save()
    run("flow.run.retry", {"id": str(failed.id)})
    with pytest.raises(Conflict) as again:
        run("flow.run.retry", {"id": str(failed.id)})
    assert again.value.code == "flow.run_not_resumable"
    assert again.value.message == str(queries.RUN_NOT_RESUMABLE)
    assert notes() == 1


def test_a_paused_automation_does_not_resume(clock):
    failed = _failed_at_the_second_step(clock)
    failed.flow.enabled = False
    failed.flow.save()
    with pytest.raises(Conflict) as paused:
        run("flow.run.retry", {"id": str(failed.id)})
    assert paused.value.code == "flow.disabled"
    failed.refresh_from_db()
    assert failed.status == FlowRun.Status.FAILED


def test_a_deleted_automation_does_not_resume(clock):
    failed = _failed_at_the_second_step(clock)
    run("flow.flow.delete", {"id": str(failed.flow_id)})
    with pytest.raises(NotFound):
        run("flow.run.retry", {"id": str(failed.id)})


def test_a_run_stopped_before_any_step_does_not_resume(clock):
    clock(NOON)
    flow = make_flow()
    stopped = make_run(
        flow,
        status=FlowRun.Status.FAILED,
        error_code="flow.loop_stopped",
        error_message="It was started by something its own steps did…",
        finished_at=NOON,
    )
    assert run("flow.run.list", {"flow_id": str(flow.id)}).rows[0].resumable is False
    with pytest.raises(Conflict) as refused:
        run("flow.run.retry", {"id": str(stopped.id)})
    assert refused.value.code == "flow.run_not_resumable"
    assert refused.value.message == str(queries.BEFORE_ANY_STEP)


def test_a_run_that_lost_what_its_steps_left_does_not_resume(clock):
    # A run that failed before this flow existed (or after its seven days): its outputs are gone.
    failed = _failed_at_the_second_step(clock)
    failed.outputs = {}
    failed.save()
    with pytest.raises(Conflict) as refused:
        run("flow.run.retry", {"id": str(failed.id)})
    assert refused.value.code == "flow.resume_expired"


def test_after_seven_days_it_no_longer_resumes_and_forgets_what_it_read(clock):
    failed = _failed_at_the_second_step(clock)
    clock(NOON + dt.timedelta(days=7, minutes=1))
    with pytest.raises(Conflict) as late:
        run("flow.run.retry", {"id": str(failed.id)})
    assert late.value.code == "flow.resume_expired"
    run("flow.run.prune", {}, ctx_for(permissions={"flow.system"}))
    failed.refresh_from_db()
    assert (failed.status, failed.outputs) == (FlowRun.Status.FAILED, {})
    assert run("flow.run.list", {"flow_id": str(failed.flow_id)}).rows[0].resumable is False


def test_the_prune_keeps_what_a_recent_failure_read(clock):
    failed = _failed_at_the_second_step(clock)
    clock(NOON + dt.timedelta(days=6))
    run("flow.run.prune", {}, ctx_for(permissions={"flow.system"}))
    failed.refresh_from_db()
    assert set(failed.outputs) == {"s1"}


def test_an_unknown_run_is_not_found():
    with pytest.raises(NotFound):
        run("flow.run.retry", {"id": "0190a000-0000-7000-8000-000000000000"})


def test_resuming_needs_the_permission_to_manage_automations(clock):
    failed = _failed_at_the_second_step(clock)
    with pytest.raises(PermissionDenied):
        run("flow.run.retry", {"id": str(failed.id)}, ctx_for(permissions={"flow.view"}))
