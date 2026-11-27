"""What of Tasks travels in an export of the business (BASE-F35): the active projects, by their code, and the open
tasks (to do, in progress or blocked) with their project, the task they are a subtask of, their priority, due date,
tags and status, read with Tasks' own lists and written with its own creates. Done or cancelled tasks, the comments and
who a task or a project is assigned to never travel: they are what already happened and the business's people.

Every test runs against the real apps, in business A's own database, as production does.
"""

import datetime as dt

import pytest

from apps.task.tests.conftest import HUB_DB, in_business_a
from base.tenancy.tests.business import A
from base.tests.blueprint_round_trip import app_report, call, data_of, loaded_back, owner_of
from base.tests.blueprint_round_trip import exported as exported_apps

__all__ = ["in_business_a"]
pytestmark = HUB_DB

DUE = dt.date(2030, 3, 2)


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def a_project(ctx):
    call(ctx, "task.project.create", code="opening", name="Opening", color="#336699")
    call(ctx, "task.task.create", title="Paint the bar", project="opening", priority="high", due_date=DUE,
         tags=["works"], description="Two coats")
    call(ctx, "task.task.create", title="Buy paint", parent="Paint the bar", project="opening")
    blocked = call(ctx, "task.task.create", title="Fix the fridge")
    call(ctx, "task.task.set_status", id=blocked.id, status="blocked")
    done = call(ctx, "task.task.create", title="Order chairs", project="opening")
    call(ctx, "task.task.set_status", id=done.id, status="done")


def the_tasks(ctx) -> list[tuple]:
    return sorted(
        (row.title, row.description, row.status, row.priority, row.due_date, row.project_name, row.parent_title,
         tuple(row.tags))
        for row in call(ctx, "task.task.list", limit=100).rows
    )  # fmt: skip


def the_projects(ctx) -> list[tuple]:
    return sorted((row.code, row.name, row.color) for row in call(ctx, "task.project.list", limit=100).rows)


def emptied(ctx) -> None:
    for row in sorted(call(ctx, "task.task.list", limit=100).rows, key=lambda row: row.parent_id is None):
        call(ctx, "task.task.delete", id=row.id)
    for row in call(ctx, "task.project.list", limit=100).rows:
        call(ctx, "task.project.delete", id=row.id)


def test_a_backup_brings_the_projects_and_the_open_tasks_back(ctx):
    a_project(ctx)
    projects = the_projects(ctx)
    open_tasks = [task for task in the_tasks(ctx) if task[2] != "done"]
    file = exported_apps(ctx, ["task"])
    emptied(ctx)

    report = loaded_back(ctx, file)

    assert (the_projects(ctx), the_tasks(ctx)) == (projects, open_tasks)
    assert {part["key"]: part["created"] for part in app_report(report, "task")["datasets"]} == {
        "task.project": 1,
        "task.task": 3,
    }


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_project(ctx)

    report = loaded_back(ctx, exported_apps(ctx, ["task"]))

    assert [(part["created"], part["already"]) for part in app_report(report, "task")["datasets"]] == [(0, 1), (0, 3)]


def test_done_tasks_comments_and_people_never_travel(ctx):
    a_project(ctx)

    data = data_of(ctx, ["task"])

    assert set(data) == {"task.project", "task.task"}
    assert sorted(row["title"] for row in data["task.task"]) == ["Buy paint", "Fix the fridge", "Paint the bar"]
    assert not {"assignee", "assigned_to_id", "owner", "owner_id"} & {key for row in data["task.task"] for key in row}
