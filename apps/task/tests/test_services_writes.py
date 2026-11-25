"""What every write on a task shares: one on a task that does not exist, or that the caller does not see, is a «does
not exist» that writes nothing and says nothing."""

import pytest
from live.errors import NotFound

from apps.task.models import Comment

from .conftest import HUB_DB, make_task
from .test_services import as_employee, as_manager, events, run

pytestmark = HUB_DB


GHOST_WRITES = [
    ("task.task.update", {"priority": "urgent"}),
    ("task.task.set_status", {"status": "blocked"}),
    ("task.task.complete", {}),
    ("task.task.assign", {"member": "Ana"}),
    ("task.task.assign", {}),
    ("task.task.delete", {}),
    ("task.comment.add", {"text": "Seen it"}),
]


@pytest.mark.parametrize("by", ["id", "number", "title"])
@pytest.mark.parametrize(("name", "extra"), GHOST_WRITES)
def test_a_write_on_a_task_that_does_not_exist_is_refused_and_says_nothing(team, name, extra, by):
    """The old module reported an assignment of a missing task as done, and the
    database's own words for a comment on one; here every write is a «does not exist», with no event."""
    real = make_task("Real one", number="TSK-20261014-0001")
    key = "task_id" if name.startswith("task.comment.") else "id"
    reference = {"id": {key: "0190c1d2-0000-7000-8000-000000000000"}, "number": {"task": "TSK-20261014-0999"}}
    reference["title"] = {"task": "ghost"}
    with pytest.raises(NotFound) as caught:
        run(name, {**reference[by], **extra}, ctx=as_manager(team))
    assert caught.value.message == "That task does not exist in this business."
    assert events() == [] and not Comment.objects.exists()
    real.refresh_from_db()
    assert (real.status, real.priority, real.assigned_to_id) == ("todo", "medium", None)


# The frontier: a colleague's task does not exist for an employee, whatever door they knock on


FOREIGN_DOORS = [
    ("task.task.detail", {}),
    ("task.task.subtasks", {}),
    ("task.comment.list", {}),
    ("task.task.update", {"priority": "urgent"}),
    ("task.task.set_status", {"status": "blocked"}),
    ("task.task.complete", {}),
    ("task.task.assign", {"to_me": True}),
    ("task.comment.add", {"text": "Seen it"}),
]


@pytest.mark.parametrize("by", ["id", "number", "title"])
@pytest.mark.parametrize(("name", "extra"), FOREIGN_DOORS)
def test_an_employee_cannot_reach_a_colleagues_task_by_any_door(team, name, extra, by):
    other = make_task("Ana's secret", number="TSK-20261014-0777", assigned_to=team["ana"])
    key = "task_id" if name.startswith("task.comment.") else "id"
    reference = {"id": {key: str(other.id)}, "number": {"task": other.number}, "title": {"task": "ana's secret"}}[by]
    with pytest.raises(NotFound):
        run(name, {**reference, **extra}, ctx=as_employee(team))
    other.refresh_from_db()
    assert (other.status, other.priority, other.assigned_to_id) == ("todo", "medium", team["ana"].id)
    assert events() == [] and not Comment.objects.exists()
    # Positive control: the manager reaches the same task through the same door.
    run(name, {**reference, **extra}, ctx=as_manager(team))
