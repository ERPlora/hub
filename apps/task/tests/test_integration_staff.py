"""Tasks with the real Staff app: the assignee and a project's owner are staff.Member records.

Staff's own operations create, rename, deactivate, link and terminate the records; the event Staff
records when someone leaves is handed to ``events.react`` as the outbox relay does, from the outbox
itself (the relay's own delivery: ``test_relay.py``).
"""

import pytest
from live.errors import InvalidPayload
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get

from apps.task import events
from apps.task.models import Task

from .conftest import A, ctx_for

pytestmark = pytest.mark.django_db


def run(name, data, ctx=None):
    op = get(name)
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate(data))


def relay(name: str) -> None:
    """Hands the last ``name`` event of the outbox to the task app's reactions."""
    event = OutboxEvent.objects.filter(name=name).latest("created_at")
    events.react(A, event.name, event.payload)


def test_a_person_created_in_staff_is_assigned_by_name_and_renamed_everywhere():
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    task = run("task.task.create", {"title": "Clean the store room", "assignee": "Ana López"})
    assert task.assigned_to_id == ana.id
    run("staff.member.update", {"id": str(ana.id), "last_name": "García"})
    # Staff's rename re-runs the task lists live, and they read the new name.
    assert "task.task.list" in live_registry.affected(["staff.member.updated"])
    assert run("task.task.detail", {"id": str(task.id)}).assignee_name == "Ana García"


def test_a_deactivated_person_takes_no_new_task():
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    run("staff.member.deactivate", {"id": str(ana.id)})
    with pytest.raises(InvalidPayload) as caught:
        run("task.task.create", {"title": "t", "assigned_to_id": str(ana.id)})
    assert caught.value.fields == {"assigned_to_id": "That person is not active in the team."}


def test_my_tasks_follow_the_record_linked_to_my_account(make_user):
    bea = make_user("bea", role="hub_employee", first_name="Bea")
    record = run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz", "user_id": bea.pk})
    run("task.task.create", {"title": "Restock shampoo", "assigned_to_id": str(record.id)})
    run("task.task.create", {"title": "Someone else's"})
    mine = run("task.task.mine", {}, ctx=ctx_for("hub_employee", actor=bea))
    assert [row.title for row in mine.rows] == ["Restock shampoo"]
    assert [row.title for row in run("task.task.list", {}, ctx=ctx_for("hub_employee", actor=bea)).rows] == [
        "Restock shampoo"
    ]


def test_terminating_a_person_in_staff_leaves_their_open_tasks_unassigned():
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    open_task = run("task.task.create", {"title": "Open", "assignee": "Ana"})
    closed = run("task.task.create", {"title": "Closed", "assignee": "Ana"})
    run("task.task.complete", {"id": str(closed.id)})
    other = run("task.task.create", {"title": "Bea's", "assignee": "Bea"})

    run("staff.member.terminate", {"id": str(ana.id), "reason": "moved away"})
    relay("staff.member.terminated")

    assert Task.objects.get(pk=open_task.id).assigned_to_id is None
    # The closed one keeps who did it; Bea's is untouched.
    assert run("task.task.detail", {"id": str(closed.id)}).assignee_name == "Ana López"
    assert Task.objects.get(pk=other.id).assigned_to_id is not None
    # A terminated record takes no new task either.
    with pytest.raises(InvalidPayload):
        run("task.task.create", {"title": "t", "assigned_to_id": str(ana.id)})
    # Delivering the event again changes nothing.
    relay("staff.member.terminated")
    assert OutboxEvent.objects.filter(name="task.task.assigned", payload__id=str(open_task.id)).count() == 1


def test_a_project_owner_is_a_staff_record():
    run("staff.member.create", {"first_name": "Marta", "last_name": "Jefa"})
    project = run("task.project.create", {"code": "opening", "name": "Opening", "owner": "Marta"})
    assert project.owner_name == "Marta Jefa"
