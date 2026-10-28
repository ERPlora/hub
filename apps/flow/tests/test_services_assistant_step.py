"""The «Ask the assistant» step (WORKBOOK FLOW-F37, F38, F39; old hub HUB-F95, HUB-F279, old SaaS SAAS_ASSISTANT-F04).

The gateway is erplora.com's assistant door that answers a turn at once (``POST /internal/assistant/chat``), served
on 127.0.0.1 by ``base.tests.fake_gateway``: the Hub calls it with its real network code, signed. The request that
reaches the step parks the run and answers at once; the worker asks the assistant after that COMMIT, outside any
transaction, with nobody in front: only the reads and actions the step names AND the automation was granted are
offered; a read runs at once and asks nobody (gh:hub#1595); a change waits in «Waiting for your answer» («Ask me
first») or runs by its own operation as the automation («On its own»). What it answers is the step's ``text``.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

from apps.flow import gateway as flow_gateway
from apps.flow.models import Flow, FlowRun, Question
from apps.task.models import Task
from base import relay
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

from .conftest import A, ctx_for, make_flow, run

pytestmark = pytest.mark.django_db

MADRID = ZoneInfo("Europe/Madrid")
NOON = dt.datetime(2026, 10, 15, 12, 0, tzinfo=MADRID)
CHAT = "/internal/assistant/chat"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}


@pytest.fixture(autouse=True)
def no_pauses(monkeypatch):
    """A retried call waits 1 s and 3 s in production; here, nothing."""
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


@pytest.fixture
def worker(monkeypatch, django_capture_on_commit_callbacks):
    """One pass of the outbox relay, as the worker runs it every tick (base.relay)."""
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def tick():
        with django_capture_on_commit_callbacks(execute=True):
            return relay.run(timezone.now())

    def request(name, data, ctx=None):
        with django_capture_on_commit_callbacks(execute=True):
            return run(name, data, ctx)

    tick.request = request
    return tick


def said(text: str, **more) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA} | more


def wants(name: str, arguments: dict, call_id: str = "call_1", token: str = "token-1") -> dict:
    call = {"type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(arguments)}
    return {"output": [call], "continuation": token, "quota": QUOTA}


def step(**more) -> dict:
    return {"id": "s1", "kind": "assistant", "prompt": "Help {{input.name}}", "tools": ["task.task.list", "task.task.create"]} | more


def manual(steps, grants=("task.task.list", "task.task.create")) -> Flow:
    return make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=list(grants))


def start(worker, flow, name="Ana"):
    return worker.request("flow.flow.run", {"id": str(flow.id), "input": {"name": name}})


def offered(seen) -> list[str]:
    return [tool["name"] for tool in seen.body["tools"]]


def test_run_now_answers_at_once_and_the_worker_asks_the_assistant(gateway, clock, worker):
    # FLOW-F38: the request never waits for the model (a web thread for up to a minute): it parks the run and
    # answers; the worker asks erplora.com, signed, naming this business, with the step's task filled in.
    clock(NOON)
    flow = manual([step(), {"id": "s2", "kind": "command", "operation": "task.task.create", "params": {"title": "{{steps.s1.text}}"}}])
    gateway.reply(CHAT, json=said("Call Ana back tomorrow"))
    ran = start(worker, flow)
    assert ran.status == "calling"
    assert gateway.sent(CHAT) == []
    worker()
    [seen] = gateway.sent(CHAT)
    assert signed(seen)
    assert seen.body["hub"] == A.key
    assert seen.body["messages"] == [{"role": "user", "content": "Help Ana"}]
    assert "nobody is watching" in seen.body["instructions"]
    done = FlowRun.objects.get(pk=ran.id)
    assert done.status == FlowRun.Status.SUCCEEDED
    assert Task.objects.get().title == "Call Ana back tomorrow"
    assert [entry["outcome"] for entry in done.log] == ["thinking", "assistant_answered", "done"]
    assert done.log[1]["text"] == "Call Ana back tomorrow"


def test_only_the_tools_the_step_names_and_the_automation_was_granted_are_offered(gateway, clock, worker):
    clock(NOON)
    flow = manual([step()], grants=["task.task.list"])
    gateway.reply(CHAT, json=said("Nothing to do"))
    start(worker, flow)
    worker()
    [seen] = gateway.sent(CHAT)
    assert offered(seen) == ["task__task__list"]


def test_a_tool_it_was_not_offered_never_runs(gateway, clock, worker):
    clock(NOON)
    flow = manual([step(mode="auto")], grants=["task.task.list"])
    gateway.reply(CHAT, json=wants("task__task__create", {"title": "Sneaky"}))
    gateway.reply(CHAT, json=said("I could not"))
    ran = start(worker, flow)
    worker()
    assert Task.objects.count() == 0
    answer = gateway.sent(CHAT)[1].body["messages"][-1]
    assert answer["role"] == "tool"
    assert json.loads(answer["content"])["error"]["code"] == "not_available"
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_hub_1595_a_read_runs_at_once_and_asks_nobody(gateway, clock, worker):
    # gh:hub#1595: an automation that only looks something up never asks a person to approve a question.
    clock(NOON)
    Task.objects.create(title="Water the plants")
    flow = manual([step()])
    gateway.reply(CHAT, json=wants("task__task__list", {}))
    gateway.reply(CHAT, json=said("You have one task"))
    ran = start(worker, flow)
    worker()
    assert Question.objects.count() == 0
    first, second = gateway.sent(CHAT)
    assert second.body["continuation"] == "token-1"  # the answer to its tools costs no other message (FLOW-F39)
    assert "Water the plants" in second.body["messages"][-1]["content"]
    done = FlowRun.objects.get(pk=ran.id)
    assert done.status == FlowRun.Status.SUCCEEDED
    assert [entry["outcome"] for entry in done.log] == ["thinking", "assistant_used", "assistant_answered"]


def test_ask_me_first_leaves_a_change_waiting_for_an_answer_and_a_yes_does_it(gateway, clock, worker):
    clock(NOON)
    flow = manual([step(), {"id": "s2", "kind": "command", "operation": "task.task.create", "params": {"title": "After"}}])
    gateway.reply(CHAT, json={**wants("task__task__create", {"title": "Call Ana"}), "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "I will leave a task."}]},
        *wants("task__task__create", {"title": "Call Ana"})["output"],
    ]})
    ran = start(worker, flow)
    worker()
    assert Task.objects.count() == 0
    waiting = FlowRun.objects.get(pk=ran.id)
    assert waiting.status == FlowRun.Status.ASKING
    question = Question.objects.get(run_id=ran.id)
    assert question.step_id == "s1"
    assert "Call Ana" in question.details
    answered = worker.request("flow.question.answer", {"id": str(question.id), "approve": True, "note": "fine"})
    assert answered.status == FlowRun.Status.SUCCEEDED
    assert sorted(Task.objects.values_list("title", flat=True)) == ["After", "Call Ana"]
    assert len(gateway.sent(CHAT)) == 1  # a yes does the change, it does not ask the model again


def test_a_no_to_the_assistants_change_does_nothing_and_cancels_the_run(gateway, clock, worker):
    clock(NOON)
    flow = manual([step()])
    gateway.reply(CHAT, json=wants("task__task__create", {"title": "Call Ana"}))
    ran = start(worker, flow)
    worker()
    question = Question.objects.get(run_id=ran.id)
    answered = worker.request("flow.question.answer", {"id": str(question.id), "approve": False})
    assert answered.status == FlowRun.Status.CANCELLED
    assert Task.objects.count() == 0


def test_on_its_own_it_does_the_change_as_the_automation_and_goes_on(gateway, clock, worker):
    clock(NOON)
    flow = manual([step(mode="auto")])
    gateway.reply(CHAT, json=wants("task__task__create", {"title": "Call Ana"}))
    gateway.reply(CHAT, json=said("Done: I left the task"))
    ran = start(worker, flow)
    worker()
    assert Question.objects.count() == 0
    assert Task.objects.get().title == "Call Ana"
    second = gateway.sent(CHAT)[1].body
    assert second["continuation"] == "token-1"
    assert second["messages"][-2]["tool_calls"][0]["function"]["name"] == "task__task__create"
    done = FlowRun.objects.get(pk=ran.id)
    assert done.status == FlowRun.Status.SUCCEEDED
    assert done.log[1] | {"at": ""} == {
        "step": "s1", "kind": "assistant", "operation": "task.task.create", "outcome": "assistant_used", "ok": True, "at": "",
    }


def test_a_change_the_automation_was_not_granted_is_refused_to_the_model(gateway, clock, worker):
    # The same refusal as the screen's: the automation's own permissions, never a person's.
    clock(NOON)
    flow = manual([step(mode="auto", tools=["task.task.create"])], grants=["task.task.create"])
    gateway.reply(CHAT, json=wants("task__task__create", {"title": ""}))
    gateway.reply(CHAT, json=said("It did not take it"))
    start(worker, flow)
    worker()
    tool = gateway.sent(CHAT)[1].body["messages"][-1]
    assert json.loads(tool["content"])["error"]["code"] == "invalid_payload"
    assert Task.objects.count() == 0


def test_the_rounds_cap_stops_the_step_and_says_so(gateway, clock, worker):
    clock(NOON)
    flow = manual([step(max_rounds=2)])
    for n in range(3):
        gateway.reply(CHAT, json=wants("task__task__list", {}, call_id=f"call_{n}", token=f"t{n}"))
    ran = start(worker, flow)
    worker()
    assert len(gateway.sent(CHAT)) == 2
    failed = FlowRun.objects.get(pk=ran.id)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.assistant_too_many_rounds")
    assert "2" in failed.error_message


def test_a_failure_the_saas_says_can_be_retried_is_retried(gateway, clock, worker):
    clock(NOON)
    flow = manual([step()])
    gateway.reply(CHAT, status=502, json={"error": {"code": "assistant.provider_unavailable", "message": "x", "retriable": True}})
    gateway.reply(CHAT, json=said("Here I am"))
    ran = start(worker, flow)
    worker()
    assert len(gateway.sent(CHAT)) == 2
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_a_spent_month_stops_the_run_with_its_reason_and_is_not_retried(gateway, clock, worker):
    clock(NOON)
    flow = manual([step()])
    refusal = {"code": "assistant.quota_exceeded", "message": "x", "retriable": False, "used": 30, "limit": 30}
    gateway.reply(CHAT, status=429, json={"error": refusal})
    ran = start(worker, flow)
    worker()
    assert len(gateway.sent(CHAT)) == 1
    failed = FlowRun.objects.get(pk=ran.id)
    assert (failed.status, failed.error_code) == (FlowRun.Status.FAILED, "flow.assistant_quota_exceeded")
    assert failed.log[-1]["outcome"] == "failed"


def test_a_gateway_that_never_answers_is_tried_three_times_then_stops_the_run(gateway, clock, worker, settings):
    clock(NOON)
    flow = manual([step()])
    for _ in range(3):
        gateway.reply(CHAT, status=502, json={"error": {"code": "assistant.provider_unavailable", "message": "x", "retriable": True}})
    ran = start(worker, flow)
    worker()
    assert len(gateway.sent(CHAT)) == 3
    assert FlowRun.objects.get(pk=ran.id).error_code == "flow.assistant_unavailable"


def test_if_it_fails_carry_on_goes_on_without_the_answer(gateway, clock, worker):
    clock(NOON)
    flow = manual([step(on_error="continue"), {"id": "s2", "kind": "command", "operation": "task.task.create", "params": {"title": "Anyway"}}])
    gateway.reply(CHAT, status=429, json={"error": {"code": "assistant.quota_exceeded", "message": "x", "retriable": False}})
    ran = start(worker, flow)
    worker()
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED
    assert Task.objects.get().title == "Anyway"


def test_a_turn_left_half_way_is_asked_again_when_its_lease_runs_out(gateway, clock, worker):
    # The process died while the assistant thought: the run is still «calling»; past the lease the minute's
    # pass asks again.
    clock(NOON)
    flow = manual([step()])
    ran = start(worker, flow)  # parked, and the worker never ran
    clock(NOON + dt.timedelta(minutes=6))
    gateway.reply(CHAT, json=said("Back"))
    worker.request("flow.run.resume_due", {})
    assert FlowRun.objects.get(pk=ran.id).status == FlowRun.Status.SUCCEEDED


def test_trying_it_says_what_it_would_ask_and_asks_nothing(gateway):
    tried = run("flow.flow.test", {"document": {"trigger": {"kind": "manual"}, "steps": [step()]}, "input": {"name": "Ana"}})
    assert tried.steps[0].outcome == "would_ask_assistant"
    assert tried.steps[0].params["prompt"] == "Help Ana"
    assert gateway.sent(CHAT) == []


def test_saving_a_tool_the_business_lacks_or_the_assistant_may_not_use_is_refused_next_to_the_step():
    from live.errors import InvalidPayload

    for tool in ("nothing.here.list", "customer.health.detail"):
        with pytest.raises(InvalidPayload) as refused:
            run("flow.flow.create", {"name": f"With {tool}", "trigger": {"kind": "manual"}, "steps": [step(tools=[tool])]}, ctx_for("hub_owner"))
        assert "steps.0.tools" in refused.value.fields
