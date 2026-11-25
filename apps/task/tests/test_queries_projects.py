"""Reads of the projects (TASK-F13): their task counts and owner, and the list's filters and sorts."""

from django.utils import timezone

from base.tests.ordering import assert_reads_backwards, listed_with

from .conftest import HUB_DB, make_project, make_task
from .test_queries import as_employee, run

pytestmark = HUB_DB


def test_projects_with_their_counts_and_owner(team):
    opening = make_project("opening", "Opening", owner=team["ana"])
    make_task("Open one", project=opening)
    make_task("Closed one", project=opening, status="done", completed_at=timezone.now())
    make_project("refit", "Refit", is_active=False)
    page = run("task.project.list", {"sort": "name"})
    rows = {row.code: (row.task_count, row.open_task_count, row.owner_name) for row in page.rows}
    assert rows == {"opening": (2, 1, "Ana López"), "refit": (0, 0, None)}
    # An employee sees the projects too.
    assert run("task.project.list", ctx=as_employee(team)).total == 2


def test_project_filters_and_sorts(team):
    make_project("b-code", "Alpha", color="#000000")
    make_project("a-code", "Beta", is_active=False, owner=team["ana"])
    names = lambda page: [row.name for row in page.rows]  # noqa: E731
    assert names(run("task.project.list", {"search": "alp"})) == ["Alpha"]
    assert names(run("task.project.list", {"search": "a-co"})) == ["Beta"]
    assert names(run("task.project.list", {"is_active": True})) == ["Alpha"]
    # Code and colour filter by «contains», like every text filter of the table.
    assert names(run("task.project.list", {"code": "B-CO"})) == ["Alpha"]
    assert names(run("task.project.list", {"color": "#0000"})) == ["Alpha"]
    assert names(run("task.project.list", {"color": "000"})) == ["Alpha"]
    assert names(run("task.project.list", {"owner_id": str(team["ana"].id)})) == ["Beta"]
    assert names(run("task.project.list", {"sort": "code"})) == ["Beta", "Alpha"]
    assert names(run("task.project.list", {"sort": "-name"})) == ["Beta", "Alpha"]


def test_tied_projects_go_by_id_in_the_lists_own_direction():
    """hub#768: a descending list is the ascending one read backwards, ties included, and its
    pages neither repeat nor lose rows."""
    by_id = sorted(make_project(f"Tie {n}").id for n in range(4))
    assert_reads_backwards(listed_with(run, "task.project.list", "is_active"), by_id)
