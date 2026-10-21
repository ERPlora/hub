"""Tasks hear Staff through the worker's outbox relay, end to end (TASK-F15).

Staff's real operation terminates a person and records ``staff.member.terminated`` in the outbox; one tick of the
worker's real loop (``base.worker.run`` → ``base.relay``) hands it to Tasks, and the person's open tasks are left
without an assignee — once: a second tick, or the same event handed over again, changes nothing. A person who
leaves in hub B leaves B's tasks only, and the notice is heard in B only.
"""

import json
import threading

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import A, B, ctx_for

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def run(name: str, data: dict, scope=A):
    """Run the operation ``name`` as an admin of ``scope``: Staff's and Tasks' own, with their permissions."""
    op = get(name)
    return op(ctx_for("hub_admin", scope=scope), op.input.model_validate(data))


def one_tick() -> None:
    """One tick of the worker's real loop."""
    stop = threading.Event()

    def wait(_seconds: float) -> bool:
        stop.set()
        return True

    now = timezone.now()
    assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0


@pytest.fixture
def tick(db, monkeypatch):
    """``one_tick`` without the SaaS (``register_apps``) and, inside the test's transaction, without releasing
    the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    return one_tick


def delivery_to_task(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Tasks."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="task")
    return row.status, row.attempts


def released(task_id) -> list[dict]:
    """The ``task.task.assigned`` events that left ``task_id`` without an assignee."""
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name="task.task.assigned", payload__id=str(task_id))
        if event.payload.get("assigned_to_id") is None
    ]


def assignee(task_id, scope=A) -> tuple[object, object]:
    """``(assigned_to_id, assignee_name)`` as the task's detail reads it."""
    detail = run("task.task.detail", {"id": str(task_id)}, scope)
    return detail.assigned_to_id, detail.assignee_name


@pytest.fixture
def team(db):
    """Ana (leaving) with a task to do, one in progress, one blocked, one done and one cancelled; Bea with one
    to do."""
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    bea = run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    todo = run("task.task.create", {"title": "Restock shampoo", "assigned_to_id": str(ana.id)})
    doing = run("task.task.create", {"title": "Clean the store room", "assigned_to_id": str(ana.id)})
    run("task.task.set_status", {"id": str(doing.id), "status": "in_progress"})
    blocked = run("task.task.create", {"title": "Call the plumber", "assigned_to_id": str(ana.id)})
    run("task.task.set_status", {"id": str(blocked.id), "status": "blocked"})
    done = run("task.task.create", {"title": "Count the till", "assigned_to_id": str(ana.id)})
    run("task.task.complete", {"id": str(done.id)})
    cancelled = run("task.task.create", {"title": "Old order", "assigned_to_id": str(ana.id)})
    run("task.task.set_status", {"id": str(cancelled.id), "status": "cancelled"})
    beas = run("task.task.create", {"title": "Fold towels", "assigned_to_id": str(bea.id)})
    return ana, bea, (todo, doing, blocked), (done, cancelled), beas


def test_a_person_terminated_in_staff_leaves_their_open_tasks_unassigned_through_the_relay(tick, team):
    ana, bea, (todo, doing, blocked), (done, cancelled), beas = team

    run("staff.member.terminate", {"id": str(ana.id), "reason": "moved away"})
    # Staff's command only records its event: the tasks wait for the relay.
    assert assignee(todo.id) == (ana.id, "Ana López")

    tick()

    assert delivery_to_task("staff.member.terminated") == ("delivered", 1)
    assert assignee(todo.id) == (None, None)
    assert assignee(doing.id) == (None, None)
    assert assignee(blocked.id) == (None, None)
    # One notice with an empty assignee per open task; the closed ones keep who did them; Bea's is untouched.
    assert released(todo.id) == [{"id": str(todo.id), "assigned_to_id": None}]
    assert released(doing.id) == [{"id": str(doing.id), "assigned_to_id": None}]
    assert released(blocked.id) == [{"id": str(blocked.id), "assigned_to_id": None}]
    assert assignee(done.id) == (ana.id, "Ana López")
    assert assignee(cancelled.id) == (ana.id, "Ana López")
    assert assignee(beas.id) == (bea.id, "Bea Ruiz")
    # The list a manager reassigns from (TASK-F07): Ana has no open task left; hers wait without an assignee.
    assert run("task.task.list", {"assigned_to_id": str(ana.id), "open": True}).rows == []
    unassigned = run("task.task.list", {"unassigned": True})
    assert sorted(row.id for row in unassigned.rows) == sorted([todo.id, doing.id, blocked.id])


def test_a_second_tick_or_the_same_notice_handed_over_again_changes_nothing(tick, team):
    ana, _bea, (todo, doing, blocked), _closed, _beas = team
    run("staff.member.terminate", {"id": str(ana.id)})
    tick()
    notices = OutboxEvent.objects.filter(name="task.task.assigned").count()

    tick()
    assert delivery_to_task("staff.member.terminated") == ("delivered", 1)

    # The same notice handed to Tasks again, as if its delivery had been lost: the relay runs it once more.
    event = OutboxEvent.objects.filter(name="staff.member.terminated").latest("id")
    EventDelivery.objects.filter(event_id=event.id, app_label="task").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )
    tick()

    assert delivery_to_task("staff.member.terminated") == ("delivered", 2)
    assert OutboxEvent.objects.filter(name="task.task.assigned").count() == notices
    assert {assignee(todo.id), assignee(doing.id), assignee(blocked.id)} == {(None, None)}


def test_a_person_without_open_tasks_leaves_and_nothing_happens(tick):
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    done = run("task.task.create", {"title": "Count the till", "assigned_to_id": str(ana.id)})
    run("task.task.complete", {"id": str(done.id)})

    run("staff.member.terminate", {"id": str(ana.id)})
    tick()

    assert delivery_to_task("staff.member.terminated") == ("delivered", 1)
    assert released(done.id) == []
    assert assignee(done.id) == (ana.id, "Ana López")


# ── Two hubs, on committed data ──────────────────────────────────────────────────────────────


@pytest.fixture
def listen(transactional_db, db_dsn):
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


def test_a_person_who_leaves_hub_b_frees_b_tasks_only_and_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"}, A)
    a_task = run("task.task.create", {"title": "Restock shampoo", "assigned_to_id": str(ana.id)}, A)
    bea = run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"}, B)
    b_task = run("task.task.create", {"title": "Fold towels", "assigned_to_id": str(bea.id)}, B)
    heard(on_a), heard(on_b)  # the creations' own notices

    run("staff.member.terminate", {"id": str(bea.id)}, B)
    heard(on_b)  # the termination's own notice
    one_tick()

    assert assignee(b_task.id, B) == (None, None)
    assert "task.task.assigned" in heard(on_b)
    assert heard(on_a) == set()
    assert assignee(a_task.id, A) == (ana.id, "Ana López")
    reaction = OutboxEvent.objects.get(name="task.task.assigned", payload__id=str(b_task.id))
    assert (reaction.scope_kind, reaction.scope_key) == (B.kind, B.key)
    # The positive control: a person who leaves hub A frees A's task, heard in A.
    run("staff.member.terminate", {"id": str(ana.id)}, A)
    heard(on_a)
    one_tick()
    assert assignee(a_task.id, A) == (None, None)
    assert "task.task.assigned" in heard(on_a)
    assert heard(on_b) == set()
