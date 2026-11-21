"""What the engine does the same way on two paths (WORKBOOK FLOW-F21, F23, F28, F36, F38).

A run parks on a question alike when an «Ask someone first» step asks it and when an «Ask the assistant» step that asks
first leaves a change waiting; it goes on alike when its wait is over and when someone says yes; and an event starts it
alike whether its «Only when…» can be read or not. Each test pins down one path: what the run is left with and the
events it records, with their data and in their order.
"""

import datetime as dt
import json
import uuid

import pytest
from live.context import system_context
from live.models import OutboxEvent

from apps.flow import events
from apps.flow.models import Flow, FlowRun, Question

from .conftest import A, HUB_DB, TASK_STEP, ctx_for, make_flow, make_run, run

pytestmark = HUB_DB

NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=2)))
#: Until when a question waits for its answer when its step says nothing: three days.
ANSWER_BY = NOON + dt.timedelta(hours=72)
CREATED = "customer.customer.created"


def recorded(since: int = 0) -> list[tuple[str, dict]]:
    """The events recorded after the first ``since``, oldest first, with their data."""
    return [(event.name, event.payload) for event in OutboxEvent.objects.order_by("created_at", "id")][since:]


def manual(*steps) -> Flow:
    return make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=list(steps), grants=["task.task.create"])


def run_now(flow: Flow) -> FlowRun:
    return FlowRun.objects.get(pk=run("flow.flow.run", {"id": str(flow.id), "input": {"name": "Ana"}}).id)


def parked_on_its_question(ran: FlowRun, flow: Flow) -> None:
    parked = FlowRun.objects.get(pk=ran.pk)
    question = Question.objects.get(run=parked)
    assert (parked.status, parked.resume_at, question.expires_at) == (FlowRun.Status.ASKING, ANSWER_BY, ANSWER_BY)
    assert recorded()[-2:] == [
        (events.QUESTION_ASKED, {"id": str(question.id), "run_id": str(parked.id), "flow_id": str(flow.id)}),
        (events.RUN_PARKED, {"id": str(parked.id), "flow_id": str(flow.id), "resume_at": ANSWER_BY.isoformat()}),
    ]


def test_an_ask_step_parks_the_run_on_its_question(clock):
    clock(NOON)
    flow = manual({"id": "s1", "kind": "ask", "title": "Call {{input.name}}?"}, TASK_STEP | {"id": "s2"})
    parked_on_its_question(run_now(flow), flow)


def test_a_change_the_assistant_asks_first_parks_the_run_on_its_question(clock):
    clock(NOON)
    flow = manual({"id": "s1", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": ["task.task.create"]})
    ran = run_now(flow)
    system = system_context(A)
    run("flow.run.claim_assistant", {"id": str(ran.id)}, system)
    call = {"call_id": "call_1", "name": "task__task__create", "arguments": json.dumps({"title": "Call Ana"})}
    run("flow.run.assistant_round", {"id": str(ran.id), "text": "I will leave a task.", "calls": [call]}, system)
    parked_on_its_question(ran, flow)


def went_on(ran: FlowRun, flow: Flow, since: int, before: list[str]) -> None:
    """``ran`` went on from where it was parked: after ``before``, it says so, its next step runs and it ends."""
    done = FlowRun.objects.get(pk=ran.pk)
    assert (done.status, done.resume_at) == (FlowRun.Status.SUCCEEDED, None)
    after = recorded(since)
    assert [name for name, _ in after] == [*before, events.RUN_RESUMED, "task.task.created", events.RUN_FINISHED]
    assert after[len(before)][1] == {"id": str(done.id), "flow_id": str(flow.id)}


def test_a_run_whose_wait_is_over_goes_on(clock):
    clock(NOON)
    flow = manual({"id": "s1", "kind": "delay", "seconds": 60}, TASK_STEP | {"id": "s2"})
    ran = run_now(flow)
    since = OutboxEvent.objects.count()
    clock(NOON + dt.timedelta(minutes=2))
    assert run("flow.run.resume_due", {}, system_context(A)).count == 1
    went_on(ran, flow, since, [])


def test_a_run_whose_question_gets_a_yes_goes_on(clock):
    clock(NOON)
    flow = manual({"id": "s1", "kind": "ask", "title": "Call {{input.name}}?"}, TASK_STEP | {"id": "s2"})
    ran = run_now(flow)
    since = OutboxEvent.objects.count()
    question = Question.objects.get(run=ran)
    run("flow.question.answer", {"id": str(question.id), "approve": True, "note": ""}, ctx_for())
    went_on(ran, flow, since, [events.QUESTION_ANSWERED])


@pytest.fixture
def chained():
    """A run of another automation: what it causes carries its chain of automations."""
    other = make_flow("Other", trigger_kind=Flow.Trigger.MANUAL)
    return make_run(other, chain=[str(uuid.uuid7())])


def started_by_the_event(flow: Flow, parent: FlowRun, event_id: uuid.UUID) -> FlowRun:
    started = FlowRun.objects.get(flow=flow)
    assert {field: getattr(started, field) for field in STARTED} == {
        "trigger_kind": Flow.Trigger.EVENT,
        "trigger_key": str(event_id),
        "event_name": CREATED,
        "input": {"name": "Ana"},
        "chain": [*parent.chain, str(parent.flow_id)],
        "started_by": "system",
        "started_at": NOON,
        "flow_version": flow.version,
        "definition": {"steps": flow.steps},
    }
    mine = [(name, data) for name, data in recorded() if data.get("id") == str(started.id)]
    assert mine[0] == (events.RUN_STARTED, {"id": str(started.id), "flow_id": str(flow.id)})
    return started


STARTED = (
    "trigger_kind",
    "trigger_key",
    "event_name",
    "input",
    "chain",
    "started_by",
    "started_at",
    "flow_version",
    "definition",
)


def test_an_event_starts_a_run_that_goes_through_its_steps(clock, chained):
    clock(NOON)
    flow = make_flow("Welcome")
    event_id = uuid.uuid7()
    events.react(A, CREATED, {"name": "Ana"}, event_id=event_id, actor=f"flow_run:{chained.id}")
    started = started_by_the_event(flow, chained, event_id)
    assert started.status == FlowRun.Status.SUCCEEDED


def test_an_event_starts_a_run_whose_only_when_it_cannot_read_and_fails_it(clock, chained):
    clock(NOON)
    flow = make_flow("Broken", trigger_filter={"input.total": {"bigger": 10}})
    event_id = uuid.uuid7()
    events.react(A, CREATED, {"name": "Ana"}, event_id=event_id, actor=f"flow_run:{chained.id}")
    started = started_by_the_event(flow, chained, event_id)
    assert (started.status, started.error_code) == (FlowRun.Status.FAILED, "flow.filter_unreadable")
