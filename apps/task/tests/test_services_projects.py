"""Writes of the projects (TASK-F12–F14): create, edit and delete one."""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.task.models import Project

from .conftest import HUB_DB, make_project, make_task
from .test_services import as_employee, as_manager, events, names, run

pytestmark = HUB_DB


def test_a_project_is_born_active_with_its_owner(team):
    project = run("task.project.create", {"code": "q3-audit", "name": "Audit", "color": "#AA3300", "owner": "Ana"})
    assert (project.is_active, project.owner_name, project.task_count) == (True, "Ana López", 0)
    assert events() == [("task.project.created", {"id": str(project.id), "code": "q3-audit"})]


def test_a_project_code_is_not_repeated(team):
    make_project(code="Q3-Audit")
    with pytest.raises(Conflict) as caught:
        run("task.project.create", {"code": "q3-audit", "name": "Again"})
    assert caught.value.code == "task.project_exists"
    assert caught.value.fields == {"code": "There is already a project with that code."}


def test_an_employee_does_not_manage_projects(team):
    with pytest.raises(PermissionDenied):
        run("task.project.create", {"code": "c", "name": "n"}, ctx=as_employee(team))


def test_a_project_edit_changes_only_what_was_sent(team):
    project = make_project(color="#000000")
    row = run("task.project.update", {"project": "opening", "is_active": False})
    assert (row.is_active, row.name, row.color, row.code) == (False, "Opening", "#000000", "opening")
    row = run("task.project.update", {"id": str(project.id), "name": "Grand opening", "owner": "Ana", "color": "#FF8800"})
    assert (row.name, row.color, row.owner_name) == ("Grand opening", "#FF8800", "Ana López")
    project.refresh_from_db()
    assert (project.name, project.color) == ("Grand opening", "#FF8800")
    row = run("task.project.update", {"id": str(project.id), "owner_id": None})
    assert row.owner_id is None
    run("task.project.update", {"id": str(project.id), "name": "Grand opening"})
    assert names() == ["task.project.updated"] * 3


def test_an_unknown_project_is_a_404():
    with pytest.raises(NotFound) as caught:
        run("task.project.update", {"project": "ghost", "name": "x"})
    assert caught.value.message == "That project does not exist in this business."


def test_deleting_a_project_keeps_its_tasks(team):
    project = make_project()
    task = make_task(project=project)
    run("task.project.delete", {"id": str(project.id)}, ctx=as_manager(team))
    task.refresh_from_db()
    assert task.project is None and not Project.objects.exists()
    assert events() == [("task.project.deleted", {"id": str(project.id), "code": "opening"})]
