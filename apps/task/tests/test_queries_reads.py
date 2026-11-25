"""What the task reads share: who sees what (an employee, their own tasks; a manager, every task) and how a task
and a project are named."""

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from .conftest import HUB_DB, ctx_for, make_project, make_task
from .test_queries import as_employee, as_manager, run, titles

pytestmark = HUB_DB


# Who sees what


def test_a_manager_sees_every_task_and_an_employee_their_own(team):
    make_task("Mine by assignment", assigned_to=team["worker_member"])
    make_task("Mine by creation", created_by=team["worker"].person, assigned_to=team["ana"])
    make_task("Ana's", assigned_to=team["ana"])
    make_task("Nobody's")
    assert sorted(titles(run("task.task.list", ctx=as_manager(team)))) == [
        "Ana's",
        "Mine by assignment",
        "Mine by creation",
        "Nobody's",
    ]
    page = run("task.task.list", ctx=as_employee(team))
    assert sorted(titles(page)) == ["Mine by assignment", "Mine by creation"]
    assert page.total == 2


def test_an_employee_without_a_staff_record_sees_what_they_created(make_user):
    lone = make_user("lone", role="hub_employee")
    make_task("Created by me", created_by=lone.person)
    make_task("Someone else's")
    assert titles(run("task.task.list", ctx=ctx_for("hub_employee", actor=lone))) == ["Created by me"]


def test_a_caller_without_a_user_and_without_view_all_sees_nothing():
    make_task()
    assert run("task.task.list", ctx=ctx_for("hub_employee")).total == 0


def test_a_task_the_employee_does_not_see_does_not_exist_for_them(team):
    other = make_task("Ana's", assigned_to=team["ana"])
    with pytest.raises(NotFound) as caught:
        run("task.task.detail", {"id": str(other.id)}, ctx=as_employee(team))
    assert caught.value.message == "That task does not exist in this business."
    assert run("task.task.detail", {"id": str(other.id)}, ctx=as_manager(team)).title == "Ana's"


def test_can_change_says_whether_the_caller_may_change_the_row(team):
    make_task("Mine", assigned_to=team["worker_member"])
    rows = {row.title: row.can_change for row in run("task.task.list", ctx=as_employee(team)).rows}
    assert rows == {"Mine": True}
    make_task("Ana's", assigned_to=team["ana"])
    viewer = ctx_for(permissions={"task.view", "task.view_all"}, actor=team["boss"])
    assert {row.can_change for row in run("task.task.list", ctx=viewer).rows} == {False}
    assert {row.can_change for row in run("task.task.list", ctx=as_manager(team)).rows} == {True}


def test_reading_needs_the_view_permission():
    with pytest.raises(PermissionDenied):
        run("task.task.list", ctx=ctx_for(permissions=set()))


# Naming a task


def test_a_task_is_found_by_number_or_title():
    task = make_task("Clean the store room", number="TSK-20261014-0007")
    for text in ("tsk-20261014-0007", "clean the store room", "store room"):
        assert run("task.task.detail", {"task": text}).id == task.id, text


def test_an_exact_title_wins_over_a_partial_one_and_an_open_task_over_a_closed_one():
    make_task("Clean the store room again")
    exact = make_task("Clean the store room")
    assert run("task.task.detail", {"task": "Clean the store room"}).id == exact.id
    make_task("Order dye", status="done", completed_at=timezone.now())
    open_one = make_task("Order dye")
    assert run("task.task.detail", {"task": "order dye"}).id == open_one.id


def test_an_ambiguous_title_names_the_candidates():
    make_task("Clean the store room", number="TSK-20261014-0001")
    make_task("Clean the kitchen", number="TSK-20261014-0002")
    with pytest.raises(Conflict) as caught:
        run("task.task.detail", {"task": "clean"})
    assert caught.value.code == "task.ambiguous_task"
    assert "TSK-20261014-0001 Clean the store room" in caught.value.message
    assert "TSK-20261014-0002 Clean the kitchen" in caught.value.message


def test_an_unknown_task_is_not_found():
    with pytest.raises(NotFound):
        run("task.task.detail", {"task": "nothing like it"})


# Naming a project


def test_a_project_is_found_by_id_code_or_name():
    project = make_project("opening", "Opening of the shop")
    for data in ({"id": str(project.id)}, {"project": "OPENING"}, {"project": "opening of the shop"}, {"project": "shop"}):
        assert run("task.project.detail", data).id == project.id, data


def test_an_ambiguous_project_name_names_the_candidates():
    make_project("a", "Summer refit")
    make_project("b", "Summer menu")
    with pytest.raises(Conflict) as caught:
        run("task.project.detail", {"project": "summer"})
    assert caught.value.code == "task.ambiguous_project"
    assert "Summer refit" in caught.value.message and "Summer menu" in caught.value.message
    with pytest.raises(NotFound) as missing:
        run("task.project.detail", {"project": "winter"})
    assert missing.value.message == "That project does not exist in this business."
