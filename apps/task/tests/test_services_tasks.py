"""Writes of the tasks (TASK-F01, F05–F09, F11). Who changes what: a manager, every task; an employee, their own
(assigned to their staff record or created by them). Nothing fails in silence: a refusal says why and writes nothing,
not even a number."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied

from apps.task.models import Comment, Task

from .conftest import HUB_DB, ctx_for, make_comment, make_member, make_project, make_task
from .test_services import as_employee, as_manager, events, names, run

pytestmark = HUB_DB


# Create (TASK-F01, F09)


def test_a_task_is_born_to_do_with_the_days_number_and_its_creator(team, today):
    task = run("task.task.create", {"title": "Clean the store room"}, ctx=as_manager(team))
    assert (task.status, task.priority, task.completed_at) == ("todo", "medium", None)
    assert task.number == f"TSK-{today:%Y%m%d}-0001"
    assert (task.created_by_id, task.created_by_name) == (team["boss"].person.pk, "Marta Jefa")
    second = run("task.task.create", {"title": "Order dye"}, ctx=as_manager(team))
    assert second.number == f"TSK-{today:%Y%m%d}-0002"
    assert events() == [
        (
            "task.task.created",
            {"id": str(task.id), "number": task.number, "project_id": None, "parent_id": None, "assigned_to_id": None},
        ),
        (
            "task.task.created",
            {"id": str(second.id), "number": second.number, "project_id": None, "parent_id": None, "assigned_to_id": None},
        ),
    ]


def test_everything_a_task_takes_by_name(team):
    make_project("opening", "Opening of the shop")
    task = run(
        "task.task.create",
        {
            "title": "Buy towels",
            "description": "White ones",
            "priority": "urgent",
            "due_date": "2026-10-20",
            "project": "opening",
            "assignee": "Ana",
            "tags": ["stock"],
        },
    )
    assert (task.project_name, task.assignee_name, task.priority, task.due_date, task.tags) == (
        "Opening of the shop",
        "Ana López",
        "urgent",
        dt.date(2026, 10, 20),
        ["stock"],
    )
    assert task.description == "White ones"


def test_a_subtask_takes_its_parents_project_unless_told(team):
    project = make_project()
    parent = make_task("Opening prep", number="TSK-20261001-0001", project=project)
    child = run("task.task.create", {"title": "Buy towels", "parent": "TSK-20261001-0001"})
    assert (child.parent_id, child.project_id) == (parent.id, project.id)
    other = make_project("other", "Other")
    told = run("task.task.create", {"title": "Sign", "parent_id": str(parent.id), "project_id": str(other.id)})
    assert told.project_id == other.id


@pytest.mark.parametrize(
    ("data", "field", "message"),
    [
        ({"project": "nowhere"}, "project", "That project does not exist in this business."),
        ({"parent": "nothing like it"}, "parent", "That task does not exist in this business."),
        ({"assignee": "Zoe"}, "assignee", "That staff member does not exist in this business."),
    ],
)
def test_a_reference_that_does_not_exist_is_a_422_and_spends_no_number(team, data, field, message, today):
    with pytest.raises(InvalidPayload) as caught:
        run("task.task.create", {"title": "t", **data})
    assert caught.value.fields == {field: message}
    assert not Task.objects.exists() and events() == []
    assert run("task.task.create", {"title": "t"}).number == f"TSK-{today:%Y%m%d}-0001"


def test_an_inactive_or_terminated_person_is_not_assigned(team):
    make_member("Ines", "Inactiva", status="inactive")
    make_member("Teo", "Baja", status="terminated")
    with pytest.raises(InvalidPayload) as inactive:
        run("task.task.create", {"title": "t", "assignee": "Ines"})
    assert inactive.value.fields == {"assignee": "That person is not active in the team."}
    with pytest.raises(InvalidPayload):
        run("task.task.create", {"title": "t", "assignee": "Teo"})


def test_an_ambiguous_person_names_the_candidates(team):
    make_member("Ana", "Ruiz")
    with pytest.raises(Conflict) as caught:
        run("task.task.create", {"title": "t", "assignee": "Ana"})
    assert caught.value.code == "staff.ambiguous_member"


def test_an_employee_creates_tasks_and_sees_them_but_not_under_a_parent_they_do_not_see(team):
    task = run("task.task.create", {"title": "Mine", "assignee": "Ana"}, ctx=as_employee(team))
    assert task.created_by_id == team["worker"].person.pk and task.can_change is True
    hidden = make_task("Ana's", assigned_to=team["ana"])
    with pytest.raises(InvalidPayload) as caught:
        run("task.task.create", {"title": "Sub", "parent_id": str(hidden.id)}, ctx=as_employee(team))
    assert "parent_id" in caught.value.fields


def test_creating_needs_the_add_permission():
    with pytest.raises(PermissionDenied):
        run("task.task.create", {"title": "t"}, ctx=ctx_for(permissions={"task.view"}))


# Update (TASK-F08)


def test_an_edit_changes_only_what_was_sent(team):
    project = make_project()
    task = make_task("Old", description="keep", project=project, due_date=dt.date(2026, 10, 1), tags=["a"])
    row = run(
        "task.task.update", {"id": str(task.id), "title": "New", "priority": "high", "due_date": None, "tags": ["b"]}
    )
    assert (row.title, row.description, row.priority, row.due_date, row.project_id, row.tags) == (
        "New",
        "keep",
        "high",
        None,
        project.id,
        ["b"],
    )
    task.refresh_from_db()
    assert (task.title, task.priority, task.due_date, task.tags) == ("New", "high", None, ["b"])
    assert events() == [("task.task.updated", {"id": str(task.id)})]
    row = run("task.task.update", {"id": str(task.id), "project_id": None})
    assert row.project_id is None


def test_an_edit_without_changes_says_nothing(team):
    task = make_task("Same", priority="high")
    run("task.task.update", {"id": str(task.id), "title": "Same", "priority": "high"})
    assert events() == []


def test_an_edit_moves_a_task_to_a_project_by_name(team):
    make_project("refit", "Summer refit")
    task = make_task()
    assert run("task.task.update", {"task": task.number, "project": "refit"}).project_name == "Summer refit"


def test_an_employee_edits_their_own_and_cannot_reach_someone_elses(team):
    mine = make_task("Mine", assigned_to=team["worker_member"])
    run("task.task.update", {"id": str(mine.id), "priority": "urgent"}, ctx=as_employee(team))
    other = make_task("Ana's", assigned_to=team["ana"])
    with pytest.raises(NotFound):
        run("task.task.update", {"id": str(other.id), "priority": "urgent"}, ctx=as_employee(team))
    viewer = ctx_for(permissions={"task.view", "task.view_all", "task.change"}, actor=team["worker"])
    with pytest.raises(PermissionDenied):
        run("task.task.update", {"id": str(other.id), "priority": "urgent"}, ctx=viewer)


# Status (TASK-F05) and complete (TASK-F06)


def test_done_stamps_the_completion_and_leaving_done_clears_it(team):
    task = make_task()
    row = run("task.task.set_status", {"id": str(task.id), "status": "in_progress"})
    assert (row.status, row.completed_at) == ("in_progress", None)
    row = run("task.task.set_status", {"id": str(task.id), "status": "done"})
    assert row.status == "done" and row.completed_at is not None
    row = run("task.task.set_status", {"id": str(task.id), "status": "blocked"})
    assert (row.status, row.completed_at) == ("blocked", None)
    assert events() == [
        ("task.task.status_changed", {"id": str(task.id), "from": "todo", "to": "in_progress"}),
        ("task.task.status_changed", {"id": str(task.id), "from": "in_progress", "to": "done"}),
        ("task.task.completed", {"id": str(task.id)}),
        ("task.task.status_changed", {"id": str(task.id), "from": "done", "to": "blocked"}),
    ]


def test_the_same_status_changes_nothing(team):
    task = make_task(status="blocked")
    run("task.task.set_status", {"id": str(task.id), "status": "blocked"})
    assert events() == []


def test_a_cancelled_task_can_be_moved_back_explicitly(team):
    task = make_task(status="cancelled")
    assert run("task.task.set_status", {"task": task.number, "status": "todo"}).status == "todo"


def test_complete_closes_an_open_task(team):
    task = make_task(status="blocked")
    row = run("task.task.complete", {"task": "Clean the store room"}, ctx=as_manager(team))
    assert row.status == "done" and row.completed_at is not None
    assert names() == ["task.task.status_changed", "task.task.completed"]


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_complete_refuses_a_closed_task_and_leaves_it_as_it_was(team, status):
    stamp = timezone.now() if status == "done" else None
    task = make_task(status=status, completed_at=stamp)
    with pytest.raises(Conflict) as caught:
        run("task.task.complete", {"id": str(task.id)})
    assert caught.value.code == "task.task_already_closed"
    assert caught.value.message == "That task is already closed, so it was left as it was."
    task.refresh_from_db()
    assert (task.status, task.completed_at) == (status, stamp)
    assert events() == []


def test_a_task_that_does_not_exist_is_a_404():
    with pytest.raises(NotFound):
        run("task.task.complete", {"task": "ghost"})
    with pytest.raises(NotFound):
        run("task.task.set_status", {"task": "ghost", "status": "done"})


def test_an_employee_completes_their_own(team):
    task = make_task(assigned_to=team["worker_member"])
    assert run("task.task.complete", {"id": str(task.id)}, ctx=as_employee(team)).status == "done"


# Assign (TASK-F07)


def test_assign_by_id_by_name_to_me_and_unassign(team):
    task = make_task()
    assert run("task.task.assign", {"id": str(task.id), "member_id": str(team["ana"].id)}).assignee_name == "Ana López"
    assert run("task.task.assign", {"id": str(task.id), "member": "Bea"}).assignee_name == "Bea Ruiz"
    mine = run("task.task.assign", {"id": str(task.id), "to_me": True}, ctx=as_manager(team))
    assert mine.assigned_to_id == team["boss_member"].id
    assert run("task.task.assign", {"id": str(task.id)}).assigned_to_id is None
    assert events("task.task.assigned") == [
        ("task.task.assigned", {"id": str(task.id), "assigned_to_id": str(team["ana"].id)}),
        ("task.task.assigned", {"id": str(task.id), "assigned_to_id": str(team["worker_member"].id)}),
        ("task.task.assigned", {"id": str(task.id), "assigned_to_id": str(team["boss_member"].id)}),
        ("task.task.assigned", {"id": str(task.id), "assigned_to_id": None}),
    ]


def test_assigning_to_whom_already_has_it_says_nothing(team):
    task = make_task(assigned_to=team["ana"])
    run("task.task.assign", {"id": str(task.id), "member": "Ana López"})
    assert events() == []


def test_to_me_without_a_staff_record_is_refused(make_user):
    lone = make_user("lone", role="hub_manager")
    task = make_task()
    with pytest.raises(InvalidPayload) as caught:
        run("task.task.assign", {"id": str(task.id), "to_me": True}, ctx=ctx_for("hub_manager", actor=lone))
    assert caught.value.fields == {"to_me": "You have no staff record: you cannot be assigned tasks."}


def test_an_employee_hands_their_task_to_a_colleague(team):
    task = make_task(assigned_to=team["worker_member"])
    row = run("task.task.assign", {"id": str(task.id), "member": "Ana"}, ctx=as_employee(team))
    assert row.assignee_name == "Ana López"
    # It is not theirs any more.
    assert row.can_change is False


# Delete (TASK-F11)


def test_deleting_a_task_takes_its_subtasks_and_comments(team):
    parent = make_task("Parent")
    make_task("Child", parent=parent)
    make_comment(parent)
    assert run("task.task.delete", {"id": str(parent.id)}, ctx=as_manager(team)).id == parent.id
    assert not Task.objects.exists() and not Comment.objects.exists()
    assert events() == [("task.task.deleted", {"id": str(parent.id), "number": parent.number})]


def test_an_employee_does_not_delete(team):
    task = make_task(assigned_to=team["worker_member"])
    with pytest.raises(PermissionDenied):
        run("task.task.delete", {"id": str(task.id)}, ctx=as_employee(team))
