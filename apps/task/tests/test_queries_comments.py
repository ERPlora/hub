"""The comments of a task (TASK-F10): the newest first with their author, and none of a task the caller does not
see."""

import pytest
from live.errors import NotFound

from .conftest import HUB_DB, make_comment, make_task
from .test_queries import as_employee, run

pytestmark = HUB_DB


def test_comments_newest_first_with_their_author(team):
    task = make_task()
    make_comment(task, "First", author=team["boss"].person)
    make_comment(task, "Second")
    page = run("task.comment.list", {"task_id": str(task.id)})
    assert [(row.text, row.author_name) for row in page.rows] == [
        ("Second", None),
        ("First", "Marta Jefa"),
    ]
    assert run("task.comment.list", {"task": task.number}).total == 2


def test_comments_of_a_task_the_employee_does_not_see_do_not_exist(team):
    task = make_task(assigned_to=team["ana"])
    with pytest.raises(NotFound):
        run("task.comment.list", {"task_id": str(task.id)}, ctx=as_employee(team))
