"""«When something happens in the business, the automation starts» (WORKBOOK FLOW-F21), end to end through the
worker's real outbox relay (``base.relay``, PLAN-HUB round 2026-10-20; ``base/tests/test_relay.py`` is the
pattern): the real Customers operation writes its event, one tick of the worker's real loop hands it to flow,
the automation runs and its task is in Tasks — once, a second tick changing nothing. An event of hub B starts
its run in B, and its notices are heard in B only (phase 1 shares the tables; the frontier is the scope).
"""

import json
import threading

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import system_context
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.flow.models import FlowRun
from apps.task.models import Task
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import A, B, run

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
