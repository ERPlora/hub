"""What the tests of the task app's writes share: how an operation is run, the events in the outbox and who runs
it; and the notification after the COMMIT, on the channel of the command's scope only. Each module of ``services/``
has its own tests, in ``test_services_<module>.py``."""

import json

import psycopg
import pytest
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.task import events as task_events
from base.tenancy.context import use_hub

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, B, ctx_for, make_task

pytestmark = HUB_DB

WAIT = 1.0
QUIET = 0.3


def run(name, data=None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def events(name=None):
    rows = OutboxEvent.objects.order_by("created_at", "id")
    if name:
        rows = rows.filter(name=name)
    return [(event.name, event.payload) for event in rows]


def names():
    return [name for name, _ in events()]


def as_employee(team):
    return ctx_for("hub_employee", actor=team["worker"])


def as_manager(team):
    return ctx_for("hub_manager", actor=team["boss"])


# Notifications: after the COMMIT, on the channel of the command's scope only


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


def received(session, timeout=WAIT, stop_after=None):
    return [
        (note.channel, json.loads(note.payload))
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@HUB_DB_COMMITTED
def test_a_command_in_scope_b_notifies_the_channel_of_b_only(listen, hub_b):
    in_a = make_task("Clean the store room")  # straight to the model: it tells nobody
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        run("task.task.create", {"title": "Clean the store room"}, ctx=ctx_for(scope=B))
        assert OutboxEvent.objects.get(name=task_events.TASK_CREATED).scope_key == B.key

    assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [task_events.TASK_CREATED]})]
    assert received(on_a, timeout=QUIET) == []

    # Positive control: the same listener of A does hear a command run in A.
    run("task.task.update", {"id": str(in_a.id), "priority": "high"}, ctx=ctx_for(scope=A))
    assert OutboxEvent.objects.get(name=task_events.TASK_UPDATED).scope_key == A.key
    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [task_events.TASK_UPDATED]})]
    assert received(on_b, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_refused_command_notifies_nobody(listen, hub_b):
    with use_hub(hub_b):
        task = make_task(status="done", completed_at=timezone.now())
    on_b = listen(B)
    with use_hub(hub_b), pytest.raises(Conflict):
        run("task.task.complete", {"id": str(task.id)}, ctx=ctx_for(scope=B))
    assert received(on_b, timeout=QUIET) == []
