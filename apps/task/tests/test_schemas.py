"""Input schemas of the task app: what a caller may send, and the 422 per field of what it may not."""

import datetime as dt
import uuid
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from apps.task.schemas import (
    AssignIn,
    CommentIn,
    PageIn,
    ProjectIn,
    ProjectPatchIn,
    SetStatusIn,
    TaskIn,
    TaskListIn,
    TaskMineIn,
    TaskPatchIn,
    TaskRefIn,
)


def errors(schema, **data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {".".join(str(p) for p in e["loc"]): e["type"] for e in caught.value.errors()}


def test_a_page_asks_for_at_most_100_rows():
    assert PageIn().limit == 50
    assert PageIn(limit=100).limit == 100
    assert "limit" in errors(PageIn, limit=101)
    assert "offset" in errors(PageIn, offset=-1)


def test_a_task_needs_a_title_and_trims_it():
    task = TaskIn(title="  Clean the store room  ")
    assert task.title == "Clean the store room"
    assert (task.priority, task.description, task.tags, task.due_date) == ("medium", "", [], None)
    assert "title" in errors(TaskIn, title="   ")
    assert "title" in errors(TaskIn, title="x" * 256)
    assert "description" in errors(TaskIn, title="t", description="x" * 5001)


def test_only_the_four_priorities():
    assert TaskIn(title="t", priority="urgent").priority == "urgent"
    assert errors(TaskIn, title="t", priority="critical") == {"priority": "literal_error"}


def test_a_due_date_is_a_day_and_a_moment_is_taken_as_its_day_in_madrid():
    assert TaskIn(title="t", due_date="2026-10-20").due_date == dt.date(2026, 10, 20)
    # 23:30 UTC on the 20th is already the 21st in Madrid (UTC+2 in October).
    assert TaskIn(title="t", due_date="2026-10-20T23:30:00Z").due_date == dt.date(2026, 10, 21)
    moment = dt.datetime(2026, 10, 20, 23, 30, tzinfo=ZoneInfo("UTC"))
    assert TaskIn(title="t", due_date=moment).due_date == dt.date(2026, 10, 21)
    # A moment without offset is the business's own clock.
    assert TaskIn(title="t", due_date="2026-10-20T23:30").due_date == dt.date(2026, 10, 20)
    assert TaskIn(title="t", due_date="").due_date is None
    assert "due_date" in errors(TaskIn, title="t", due_date="2026-02-30")
    assert "due_date" in errors(TaskIn, title="t", due_date="tomorrow")
    assert "due_date" in errors(TaskIn, title="t", due_date="0001-01-01")


def test_tags_are_trimmed_kept_once_and_capped():
    assert TaskIn(title="t", tags=[" stock ", "stock", "urgent"]).tags == ["stock", "urgent"]
    assert "tags.0" in errors(TaskIn, title="t", tags=[""])
    assert "tags" in errors(TaskIn, title="t", tags=[f"t{n}" for n in range(21)])


def test_a_task_is_named_by_id_or_by_text():
    assert TaskRefIn(task=" TSK-20261014-0001 ").task == "TSK-20261014-0001"
    the_id = uuid.uuid7()
    assert TaskRefIn(id=the_id).id == the_id
    assert errors(TaskRefIn) == {"task": "value_error"}


def test_a_status_change_names_one_of_the_five():
    assert SetStatusIn(task="x", status="blocked").status == "blocked"
    assert errors(SetStatusIn, task="x", status="paused") == {"status": "literal_error"}


def test_an_assignment_takes_one_person_or_none():
    assert AssignIn(task="x").member is None  # nobody: unassign
    assert AssignIn(task="x", member="Ana").member == "Ana"
    assert AssignIn(task="x", to_me=True).to_me is True
    assert "to_me" in errors(AssignIn, task="x", member="Ana", to_me=True)
    assert "member" in errors(AssignIn, task="x", member_id=str(uuid.uuid7()), member="Ana")


def test_a_patch_knows_what_was_sent():
    patch = TaskPatchIn(task="x", due_date=None, priority="high")
    assert patch.model_fields_set == {"task", "due_date", "priority"}
    assert "title" in errors(TaskPatchIn, task="x", title="")


def test_a_comment_needs_text():
    assert CommentIn(task="x", text=" ok ").text == "ok"
    assert "text" in errors(CommentIn, task="x", text="  ")
    assert "text" in errors(CommentIn, task="x", text="x" * 5001)
    assert errors(CommentIn, text="x") == {"task": "value_error"}


def test_a_project_needs_code_and_name_and_a_hex_colour():
    project = ProjectIn(code=" q3-audit ", name=" Audit ", color="#AA3300")
    assert (project.code, project.name, project.color) == ("q3-audit", "Audit", "#AA3300")
    assert ProjectIn(code="c", name="n").color == ""
    assert "code" in errors(ProjectIn, code="", name="n")
    assert "code" in errors(ProjectIn, code="x" * 41, name="n")
    assert "name" in errors(ProjectIn, code="c", name="x" * 201)
    assert "color" in errors(ProjectIn, code="c", name="n", color="red; background:url(x)")
    assert "name" in errors(ProjectPatchIn, project="c", name=" ")
    assert errors(ProjectPatchIn, name="n") == {"project": "value_error"}


def test_the_lists_declare_their_filters_and_sorts():
    assert TaskListIn().sort == "-created_at"
    assert TaskListIn(sort="priority").sort == "priority"
    assert errors(TaskListIn, sort="colour") == {"sort": "literal_error"}
    assert "status" in errors(TaskListIn, status="paused")
    assert TaskMineIn(due_within_days=7).due_within_days == 7
    assert "due_within_days" in errors(TaskMineIn, due_within_days=-1)
