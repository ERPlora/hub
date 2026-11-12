"""A run parked on something outside the Hub goes out as its own business, whichever way the worker reaches it
(FLOW-F27, F37, F38).

«Ask the assistant» and «Call another system» park their run with its wait already over (``resume_at`` = now): nobody
holds it yet. Two ways reach it: the outbox relay (``flow.run.parked`` → ``flow.run.call``) and the minute's sweep
(``flow.run.resume_due``), which is also what sends again a step whose process died. Here they go as production does:
``base.worker._hubs``, each business in its own database and on its own scope, never the worker's fixed one
(``WORKER_SCOPE_SLUG``), so what the customer gets never depends on the minute a tick lands on. Neither way gives two
turns or two calls: the claim of the step holds it for one.

Real databases, committed: the session's ``hub_a`` and ``hub_b``. The suite's ``legacy.worker_pass`` is not this path:
with every business's rows in one database, it runs the tasks on the scope of one of them.
"""

import datetime as dt
import itertools
import threading
import time

import pytest
from django.conf import settings
from django.utils import timezone
from live import operations as live_operations
from live.context import Scope, system_context
from live.models import OutboxEvent

from apps.flow import gateway as flow_gateway
from apps.flow import http, services
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task
from apps.whatsapp_inbox.models import Message
from apps.whatsapp_inbox.tests.conftest import inbound, system
from base import outbound, worker
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import TASK_STEP, ctx_for, make_flow, run
from .local_https import Handler

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]

CHAT = "/internal/assistant/chat"
SEND = "/internal/whatsapp/send"
NOTIFY = "whatsapp_inbox.message.notify"
QUOTA = {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False}
THEN_A_TASK = TASK_STEP | {"id": "s2"}
#: What erplora.com says of a business's connected number, room left in its month.
CONNECTED = {"version": 1, "status": "connected", "phone_number": "+34910000000", "monthly_limit": 150, "monthly_usage": 10}
#: The most a test waits for the worker's own thread to end a step.
THREAD_WAIT_SECONDS = 10


@pytest.fixture(autouse=True)
def a_worker_just_started(monkeypatch):
    """Nothing scheduled yet in this process, a pass that serves every hub however slow the machine, no retry pauses."""
    monkeypatch.setattr(worker, "_synced", set())
    monkeypatch.setattr(worker, "_next_hub", None)
    monkeypatch.setattr(worker, "HUB_PASS_SECONDS", 3600)
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))


@pytest.fixture
def tick(hub_a, hub_b):
    """``tick()``: one real pass of the worker over the hubs, past the minute of the last one, so ``flow.resume_due`` is
    due in it. The first pass, here, writes each hub's schedule (each task due at its next time)."""
    start = timezone.now()
    with use_control():
        worker._hubs(start)
    minutes = itertools.count(2, 2)

    def one() -> None:
        with use_control():
            worker._hubs(start + dt.timedelta(minutes=next(minutes)))

    return one


@pytest.fixture
def told(monkeypatch):
    """Every live notice sent after a COMMIT: ``(scope key, event names)``."""
    sent: list[tuple[str, list[str]]] = []
    real = live_operations.notify_hook

    def hook(scope, names):
        sent.append((scope.key, list(names)))
        if real is not None:
            real(scope, names)

    monkeypatch.setattr(live_operations, "notify_hook", hook)
    return sent


class HeldJobs:
    """``base.outbound``'s pool holding what it is asked, without leaving out a repeated job: the relay's and the sweep's
    are both asked before either is made, which the real threads only do when they happen to race."""

    def __init__(self) -> None:
        self.jobs = []

    def submit(self, job) -> bool:
        self.jobs.append(job)
        return True

    def stop(self, grace: float) -> bool:
        return True


@pytest.fixture
def held(monkeypatch):
    pool = HeldJobs()
    monkeypatch.setattr(outbound, "_pool", pool)
    return pool


def scope_of(hub) -> Scope:
    return Scope("host", hub.slug)


def said(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}], "continuation": None, "quota": QUOTA}


def assistant_step(hub) -> dict:
    return {"id": "s1", "kind": "assistant", "prompt": f"Help {hub.slug}", "tools": ["task.task.list"]}


def parked(hub, steps: list[dict], grants: list[str]):
    """«Run now» in ``hub`` with its COMMIT: the run waits on the outside and its ``flow.run.parked`` waits for the relay."""
    with use_hub(hub):
        flow = make_flow(trigger_kind=Flow.Trigger.MANUAL, steps=steps, grants=grants)
        ran = run("flow.flow.run", {"id": str(flow.id), "input": {}}, ctx_for("hub_owner", scope_of(hub)))
    assert ran.status == FlowRun.Status.CALLING
    return ran.id


def on_the_assistant(hub):
    return parked(hub, [assistant_step(hub), THEN_A_TASK], ["task.task.list", "task.task.create"])


def on_a_call(hub, origin: str):
    call = {"id": "s1", "kind": "http", "method": "POST", "url": f"{origin}/orders", "timeout": 5}
    return parked(hub, [call, THEN_A_TASK], [f"http:{origin}", "task.task.create"])


def relay_already_passed(hub) -> None:
    """The relay took its ``flow.run.parked`` and its job was lost (its queue full, the worker stopped): only the minute's
    sweep can reach the run, as when the sweep gets there first."""
    with use_hub(hub):
        OutboxEvent.objects.filter(name="flow.run.parked").update(delivered_at=timezone.now())


def turns(gateway) -> list[str]:  # noqa: F811 - the fixture
    return [seen.body["hub"] for seen in gateway.sent(CHAT)]


def went_on_in_its_business_alone(run_id, hub, other, told) -> None:
    """The run ended in ``hub``, the step after the wait on its scope too; nothing of it reached ``other``, or the worker's
    fixed scope."""
    with use_hub(hub):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.SUCCEEDED
        assert Task.objects.count() == 1
        assert set(OutboxEvent.objects.values_list("scope_key", flat=True)) == {hub.slug}
    with use_hub(other):
        assert not FlowRun.objects.exists()
        assert not Task.objects.exists()
    assert {key for key, _names in told} == {hub.slug}


def test_no_hub_of_these_tests_is_the_workers_fixed_scope(hub_a, hub_b):
    # What the tests below mean: a business that is not the one the worker's scope names.
    assert settings.WORKER_SCOPE_SLUG not in {hub_a.slug, hub_b.slug}


def test_the_sweep_asks_the_assistant_as_the_business_of_the_run(gateway, hub_a, hub_b, tick, told):  # noqa: F811
    gateway.reply(CHAT, json=said("Done"))
    run_id = on_the_assistant(hub_b)
    relay_already_passed(hub_b)
    told.clear()

    tick()

    assert turns(gateway) == [hub_b.slug]
    went_on_in_its_business_alone(run_id, hub_b, hub_a, told)


def test_the_sweep_makes_the_call_as_the_business_of_the_run(trusted, hub_a, hub_b, tick, told):
    run_id = on_a_call(hub_b, trusted)
    relay_already_passed(hub_b)
    told.clear()

    tick()

    assert len(Handler.seen) == 1
    went_on_in_its_business_alone(run_id, hub_b, hub_a, told)


def test_what_the_assistant_answers_reaches_the_customer_past_the_minute(gateway, hub_a, hub_b, tick):  # noqa: F811
    """The symptom: the guest got the thanks and never the answer, and the run ended in ``failed`` with
    ``whatsapp_inbox.channel_not_connected``, because the turn went on as the platform hub, which has no number."""
    scope = scope_of(hub_b)
    with use_hub(hub_b):
        system("whatsapp_inbox.channel.sync", CONNECTED | {"usage_month": timezone.now().strftime("%Y-%m")}, scope)
        system("whatsapp_inbox.message.receive", inbound("wamid.IN", "34600111222", sent_at=timezone.now().isoformat()), scope)
    gateway.reply(CHAT, json=said("Table for four at nine"))
    gateway.reply(SEND, json={"wa_message_id": "wamid.OUT0"})
    answer = {"id": "s2", "kind": "command", "operation": NOTIFY, "params": {"phone": "+34600111222", "text": "{{steps.s1.text}}"}}
    run_id = parked(hub_b, [assistant_step(hub_b), answer], ["task.task.list", NOTIFY])
    relay_already_passed(hub_b)

    tick()

    assert turns(gateway) == [hub_b.slug]
    with use_hub(hub_b):
        ended = FlowRun.objects.get(pk=run_id)
        assert (ended.status, ended.error_code) == (FlowRun.Status.SUCCEEDED, "")
        assert list(Message.objects.filter(direction="outbound").values_list("body", flat=True)) == ["Table for four at nine"]
    [sent] = gateway.sent(SEND)
    assert sent.body["hub"] == hub_b.slug


def test_each_business_gets_its_own_turn_of_the_same_sweep(gateway, hub_a, hub_b, tick):  # noqa: F811
    gateway.reply(CHAT, json=said("Done"))
    gateway.reply(CHAT, json=said("Done"))
    in_a, in_b = on_the_assistant(hub_a), on_the_assistant(hub_b)
    relay_already_passed(hub_a)
    relay_already_passed(hub_b)

    tick()

    asked = {seen.body["messages"][0]["content"]: seen.body["hub"] for seen in gateway.sent(CHAT)}
    assert asked == {f"Help {hub_a.slug}": hub_a.slug, f"Help {hub_b.slug}": hub_b.slug}
    for hub, run_id, other in ((hub_a, in_a, in_b), (hub_b, in_b, in_a)):
        with use_hub(hub):
            assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.SUCCEEDED
            assert not FlowRun.objects.filter(pk=other).exists()


def both_ways_in_one_tick(held, hub) -> None:
    """The relay's job and the sweep's, both for ``hub``, both asked in the same tick and neither made."""
    assert [(job.args[0], job.database.hub.slug) for job in held.jobs] == [(scope_of(hub), hub.slug)] * 2


def second_goes_while_the_first_waits(held, monkeypatch, module, name: str) -> None:
    """Makes the first job; while it waits on the outside (``module.name``), with the step held, the second one goes."""
    first, *rest = held.jobs
    real = getattr(module, name)

    def waits(*args, **kwargs):
        while rest:
            rest.pop().run()
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, waits)
    first.run()


def test_the_relay_and_the_sweep_in_one_tick_give_one_turn(gateway, held, hub_a, hub_b, tick, told, monkeypatch):  # noqa: F811
    gateway.reply(CHAT, json=said("Done"))
    run_id = on_the_assistant(hub_b)
    told.clear()

    tick()

    both_ways_in_one_tick(held, hub_b)
    assert held.jobs[0].fn is services.dispatch_assistant
    second_goes_while_the_first_waits(held, monkeypatch, flow_gateway, "turn")
    assert turns(gateway) == [hub_b.slug]
    went_on_in_its_business_alone(run_id, hub_b, hub_a, told)


def test_the_relay_and_the_sweep_in_one_tick_give_one_call(trusted, held, hub_a, hub_b, tick, told, monkeypatch):
    run_id = on_a_call(hub_b, trusted)
    told.clear()

    tick()

    both_ways_in_one_tick(held, hub_b)
    assert held.jobs[0].fn is services.dispatch_call
    second_goes_while_the_first_waits(held, monkeypatch, http, "call")
    assert len(Handler.seen) == 1
    went_on_in_its_business_alone(run_id, hub_b, hub_a, told)


def lease_ran_out(hub, run_id) -> None:
    with use_hub(hub):
        FlowRun.objects.filter(pk=run_id).update(resume_at=timezone.now() - dt.timedelta(seconds=1))


def test_a_turn_whose_process_died_waits_for_its_lease_and_goes_again_as_its_business(gateway, hub_a, hub_b, tick):  # noqa: F811
    gateway.reply(CHAT, json=said("Done"))
    run_id = on_the_assistant(hub_b)
    relay_already_passed(hub_b)
    with use_hub(hub_b):
        assert run("flow.run.claim_assistant", {"id": str(run_id)}, system_context(scope_of(hub_b))).claimed

    tick()

    assert turns(gateway) == []  # someone holds it: nobody knows yet that it died
    with use_hub(hub_b):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.CALLING

    lease_ran_out(hub_b, run_id)
    tick()

    assert turns(gateway) == [hub_b.slug]
    with use_hub(hub_b):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.SUCCEEDED


def test_a_call_whose_process_died_waits_for_its_lease_and_goes_again_as_its_business(trusted, hub_a, hub_b, tick):
    run_id = on_a_call(hub_b, trusted)
    relay_already_passed(hub_b)
    with use_hub(hub_b):
        assert run("flow.run.claim_call", {"id": str(run_id)}, system_context(scope_of(hub_b))).claimed

    tick()

    assert Handler.seen == []  # someone holds it: nobody knows yet that it died
    with use_hub(hub_b):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.CALLING

    lease_ran_out(hub_b, run_id)
    tick()

    assert len(Handler.seen) == 1
    with use_hub(hub_b):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.SUCCEEDED


def still_parked(hub, run_id) -> bool:
    with use_hub(hub):
        return FlowRun.objects.get(pk=run_id).status == FlowRun.Status.CALLING


@pytest.mark.outbound_threads
def test_in_the_workers_own_threads_it_goes_once_in_its_business(gateway, hub_a, hub_b, tick):  # noqa: F811
    # A thread of the pool starts with no context: the job enters the one of the operation that asked.
    gateway.reply(CHAT, json=said("Done"))
    run_id = on_the_assistant(hub_b)

    tick()

    deadline = time.monotonic() + THREAD_WAIT_SECONDS
    idle = threading.Event()
    while still_parked(hub_b, run_id) and time.monotonic() < deadline:
        idle.wait(0.05)
    assert outbound.stop(THREAD_WAIT_SECONDS)  # nothing left running that could still ask again
    assert turns(gateway) == [hub_b.slug]
    with use_hub(hub_b):
        assert FlowRun.objects.get(pk=run_id).status == FlowRun.Status.SUCCEEDED
