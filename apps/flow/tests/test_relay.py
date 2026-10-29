"""«When something happens in the business, the automation starts» (WORKBOOK FLOW-F21), end to end through the
worker's real outbox relay (``base.relay``, PLAN-HUB round 2026-10-20; ``base/tests/test_relay.py`` is the
pattern): the real Customers operation writes its event, one tick of the worker's real loop hands it to flow,
the automation runs and its task is in Tasks — once, a second tick changing nothing. An event of hub B starts
its run in B, and its notices are heard in B only (phase 1 shares the tables; the frontier is the scope). A call to
another system that answers late (FLOW-F27) holds neither the relay's other deliveries nor the scheduled tasks: the
worker makes it in a thread of its own (``base.outbound``), and it is still made once.
"""

import datetime as dt
import json
import threading
import time
from types import SimpleNamespace

import psycopg
import pytest
from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import system_context
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.flow import gateway as flow_gateway
from apps.flow import http
from apps.flow.models import Flow, FlowRun
from apps.task.models import Task
from base import catalog, relay, scheduler, worker
from base.catalog import RegisterResult
from base.models import EventDelivery
from base.tests.fake_gateway import gateway  # noqa: F401 - the fixture

from .conftest import A, B, make_flow, run
from .local_https import Handler

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
WELCOME = {
    "name": "Welcome",
    "trigger": {"kind": "event", "event": "customer.customer.created"},
    "steps": [
        {"id": "s1", "kind": "command", "operation": "task.task.create", "params": {"title": "Welcome {{input.id}}"}}
    ],
}


def automation(document: dict = WELCOME) -> str:
    """An automation as the owner makes it: created, granted and turned on through its operations."""
    created = run("flow.flow.create", document)
    run("flow.flow.grant", {"id": str(created.id), "operations": ["task.task.create"]})
    run("flow.flow.set_enabled", {"id": str(created.id), "enabled": True})
    return str(created.id)


def tick() -> None:
    """One tick of the worker's real loop (relay included)."""
    stop = threading.Event()
    now = timezone.now()
    assert worker.run(stop, tick_seconds=0, wait=lambda _seconds: stop.set() or True, clock=lambda: now) == 0


@pytest.fixture
def worker_loop(monkeypatch):
    """The worker without the SaaS (``register_apps``) and, inside a test's transaction, without releasing the
    connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    return tick


@pytest.mark.django_db
def test_a_new_customer_starts_the_automation_through_the_workers_relay_once(worker_loop):
    flow_id = automation()
    ana = run("customer.customer.create", {"name": "Ana López"}, system_context(A))
    event = OutboxEvent.objects.get(name="customer.customer.created")
    assert not FlowRun.objects.exists()  # nothing runs inside the request that created the card

    worker_loop()

    assert EventDelivery.objects.get(event_id=event.id, app_label="flow").status == "delivered"
    started = FlowRun.objects.get(flow_id=flow_id)
    assert (started.trigger_kind, started.trigger_key, started.event_name, started.status) == (
        "event",
        str(event.id),
        "customer.customer.created",
        "succeeded",
    )
    assert list(Task.objects.values_list("title", flat=True)) == [f"Welcome {ana.id}"]
    worker_loop()
    assert (FlowRun.objects.count(), Task.objects.count()) == (1, 1)


@pytest.mark.django_db
def test_a_paused_automation_or_another_event_starts_nothing(worker_loop):
    flow_id = automation()
    run("flow.flow.set_enabled", {"id": flow_id, "enabled": False})
    run("customer.customer.create", {"name": "Ana López"}, system_context(A))
    worker_loop()
    assert not FlowRun.objects.exists()
    run("flow.flow.set_enabled", {"id": flow_id, "enabled": True})
    run("task.task.create", {"title": "Not a customer"}, system_context(A))  # another app's event: not this one
    worker_loop()
    assert not FlowRun.objects.exists()  # and what came while it was paused is not started later


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


@pytest.mark.django_db(transaction=True)
def test_an_event_of_hub_b_starts_its_run_in_b_and_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    automation()
    on_a, on_b = listen(A), listen(B)
    run("customer.customer.create", {"name": "Bea Ruiz"}, system_context(B))
    heard(on_b)  # the card's own notice

    tick()

    assert {"flow.run.started", "flow.run.finished", "task.task.created"} <= heard(on_b)
    assert heard(on_a, timeout=0.3) == set()
    started = OutboxEvent.objects.get(name="flow.run.started")
    assert (started.scope_kind, started.scope_key) == (B.kind, B.key)
    # The positive control: a card of A is heard in A.
    run("customer.customer.create", {"name": "Ana López"}, system_context(A))
    heard(on_a)
    tick()
    assert "flow.run.started" in heard(on_a)


# ── A late answer of another system holds nothing else (FIX-HUB-BASE-RELAY-BLOCKED-BY-SLOW-REACTION-CALLS) ──────────
# One relay serves every hub of phase 1, and Django runs what a reaction leaves for after its COMMIT right there, in
# the relay's loop: a «Call another system» step of hub A that took its 30 s held every delivery of every hub, and a
# call the tick sent again held the scheduled tasks. The other system here answers only once the test lets it (5 s at
# most: a worker that waits for it fails the test instead of hanging), so the order says who waited for whom.

#: The most a test waits for the call made in the worker's thread.
CALL_WAIT_SECONDS = 10


def answering_late(monkeypatch, module, name: str) -> SimpleNamespace:
    """``module.name`` (the call to another system, a turn of the assistant) answers once ``.answer`` is set (5 s at
    most); ``.timeline`` says, in order, what happened meanwhile and when it came back (``"answered"``), and ``.held``
    whether the thread that waited for it held a database connection meanwhile."""
    timeline: list[str] = []
    held: list[bool] = []
    answer = threading.Event()
    real = getattr(module, name)

    def late(*args, **kwargs):
        held.append(connection.connection is not None)
        answer.wait(timeout=5)
        reply = real(*args, **kwargs)
        timeline.append("answered")
        return reply

    monkeypatch.setattr(module, name, late)
    return SimpleNamespace(timeline=timeline, held=held, answer=answer)


@pytest.fixture
def late_answer(monkeypatch):
    """The other system of «Call another system» answers late."""
    return answering_late(monkeypatch, http, "call")


def parked_on_a_call(origin: str) -> FlowRun:
    """A run of hub A on «Call another system», as «Run now» leaves it: committed, its call not made yet."""
    flow = make_flow(
        trigger_kind=Flow.Trigger.MANUAL,
        steps=[{"id": "s1", "kind": "http", "method": "POST", "url": f"{origin}/orders", "timeout": 5}],
        grants=[f"http:{origin}"],
    )
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    assert ran.status == FlowRun.Status.CALLING
    return FlowRun.objects.get(pk=ran.id)


def heard_by_hub_b(monkeypatch, late) -> None:
    """Every delivery of hub B goes on the timeline, and the first one lets the other system answer."""
    real = relay.deliver

    def deliver(app_label, event):
        done = real(app_label, event)
        if event.scope_key == B.key:
            late.timeline.append(f"{app_label} got {event.name} in b")
            late.answer.set()
        return done

    monkeypatch.setattr(relay, "deliver", deliver)


def went_on(parked: FlowRun) -> None:
    """The run, whose call (or turn) the worker's thread made, went on to its end."""
    deadline = time.monotonic() + CALL_WAIT_SECONDS
    while FlowRun.objects.get(pk=parked.pk).status == FlowRun.Status.CALLING and time.monotonic() < deadline:
        time.sleep(0.05)
    assert FlowRun.objects.get(pk=parked.pk).status == FlowRun.Status.SUCCEEDED


def made_once(parked: FlowRun) -> None:
    """The call, made in the worker's thread, went out once and the run went on."""
    went_on(parked)
    assert len(Handler.seen) == 1


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_a_late_call_of_hub_a_never_holds_the_deliveries_of_hub_b(trusted, late_answer, monkeypatch):
    parked = parked_on_a_call(trusted)  # its flow.run.parked is the oldest event: the relay hands it over first
    run("customer.customer.create", {"name": "Bea Ruiz"}, system_context(B))
    heard_by_hub_b(monkeypatch, late_answer)

    relay.run(timezone.now())

    made_once(parked)
    assert late_answer.timeline[0] == "flow got customer.customer.created in b"
    assert late_answer.timeline.count("answered") == 1
    assert late_answer.held == [False]  # it waited on the other system with no connection held
    parked_event = OutboxEvent.objects.get(name="flow.run.parked")
    assert EventDelivery.objects.get(event=parked_event, app_label="flow").status == "delivered"


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_a_call_sent_again_by_the_tick_never_holds_the_relay(trusted, late_answer, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    parked = parked_on_a_call(trusted)
    # The worker that took its flow.run.parked died before the call: the event is delivered, the call never went out.
    OutboxEvent.objects.filter(name="flow.run.parked").update(delivered_at=timezone.now())
    run("customer.customer.create", {"name": "Bea Ruiz"}, system_context(B))
    heard_by_hub_b(monkeypatch, late_answer)
    now = timezone.now() + dt.timedelta(minutes=1)
    scheduler.sync(now - dt.timedelta(minutes=2))  # flow.resume_due is due at the tick

    # One tick of the worker's real loop: the scheduled tasks (resume_due sends the call again), then the relay.
    stop = threading.Event()
    assert worker.run(stop, tick_seconds=0, wait=lambda _seconds: stop.set() or True, clock=lambda: now) == 0

    made_once(parked)
    assert late_answer.timeline[0] == "flow got customer.customer.created in b"
    assert late_answer.timeline.count("answered") == 1


@pytest.mark.outbound_threads
@pytest.mark.django_db(transaction=True)
def test_a_slow_assistant_of_hub_a_never_holds_the_deliveries_of_hub_b(gateway, monkeypatch):  # noqa: F811
    # «Ask the assistant» (FLOW-F37): up to a minute a turn, a few turns a step.
    monkeypatch.setattr(flow_gateway, "PAUSES", (0, 0))
    late = answering_late(monkeypatch, flow_gateway, "turn")
    gateway.reply("/internal/assistant/chat", json={
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Call Ana back tomorrow"}]}],
        "continuation": None,
        "quota": {"used": 1, "limit": 30, "resets_at": "2026-11-01T00:00:00Z", "demo": False},
    })
    flow = make_flow(
        trigger_kind=Flow.Trigger.MANUAL,
        steps=[{"id": "s1", "kind": "assistant", "prompt": "Help", "tools": ["task.task.list"]}],
        grants=["task.task.list"],
    )
    ran = run("flow.flow.run", {"id": str(flow.id), "input": {}})
    assert ran.status == FlowRun.Status.CALLING
    run("customer.customer.create", {"name": "Bea Ruiz"}, system_context(B))
    heard_by_hub_b(monkeypatch, late)

    relay.run(timezone.now())

    went_on(FlowRun.objects.get(pk=ran.id))
    assert late.timeline[0] == "flow got customer.customer.created in b"
    assert late.timeline.count("answered") == 1
    assert late.held == [False]  # each turn waits on the assistant with no connection held
