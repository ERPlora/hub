"""Reads of the tasks (TASK-F02 to F04): what a row carries, the list's filters and sorts, my tasks and the
subtasks; and nothing of a task the caller does not see leaks through a row of one they do see."""

import datetime as dt

from django.utils import timezone

from apps.task.models import Task

from .conftest import HUB_DB, ctx_for, make_comment, make_project, make_task
from .test_queries import as_employee, as_manager, run, titles

pytestmark = HUB_DB


# A row


def test_a_row_carries_its_project_parent_assignee_creator_and_counts(team):
    project = make_project("opening", "Opening", color="#AA3300")
    parent = make_task("Opening prep", number="TSK-20261014-0001", project=project)
    task = make_task(
        "Buy towels",
        project=project,
        parent=parent,
        assigned_to=team["ana"],
        created_by=team["boss"].person,
        due_date=dt.date(2026, 10, 20),
        tags=["stock"],
    )
    make_task("Pick the colour", parent=task)
    make_comment(task)
    make_comment(task)
    row = run("task.task.detail", {"id": str(task.id)})
    assert (row.project_name, row.project_color, row.parent_number, row.parent_title) == (
        "Opening",
        "#AA3300",
        "TSK-20261014-0001",
        "Opening prep",
    )
    assert (row.assignee_name, row.created_by_name, row.created_by_id) == (
        "Ana López",
        "Marta Jefa",
        team["boss"].person.pk,
    )
    assert (row.subtask_count, row.comment_count, row.tags, row.due_date) == (
        1,
        2,
        ["stock"],
        dt.date(2026, 10, 20),
    )


def test_a_creator_without_a_name_reads_as_their_email_or_username(make_user):
    plain = make_user("plain")
    task = make_task(created_by=plain.person)
    assert run("task.task.detail", {"id": str(task.id)}).created_by_name == "plain"


# The list's filters and sorts


def test_search_looks_in_number_title_description_assignee_and_project(team):
    make_task("Towels", number="TSK-20261014-0042")
    make_task("Chairs", description="the blue ones")
    make_task("Mop", assigned_to=team["ana"])
    make_task("Sign", project=make_project("refit", "Summer refit"))
    for text, expected in (
        ("20261014-0042", ["Towels"]),
        ("blue", ["Chairs"]),
        ("ana lóp", ["Mop"]),
        ("summer", ["Sign"]),
        ("refit", ["Sign"]),
    ):
        assert titles(run("task.task.list", {"search": text})) == expected, text


def test_filters_by_status_priority_and_open(team):
    now = timezone.now()
    make_task("A", status="todo", priority="urgent")
    make_task("B", status="in_progress", priority="low")
    make_task("C", status="done", completed_at=now)
    make_task("D", status="cancelled")
    assert titles(run("task.task.list", {"status": "in_progress"})) == ["B"]
    assert titles(run("task.task.list", {"priority": "urgent"})) == ["A"]
    assert sorted(titles(run("task.task.list", {"open": True}))) == ["A", "B"]
    assert sorted(titles(run("task.task.list", {"open": False}))) == ["C", "D"]


def test_overdue_is_open_and_due_before_the_business_today(today):
    yesterday = today - dt.timedelta(days=1)
    make_task("Late", due_date=yesterday)
    make_task("Today", due_date=today)
    make_task("Late but done", due_date=yesterday, status="done", completed_at=timezone.now())
    assert titles(run("task.task.list", {"overdue": True})) == ["Late"]


def test_filters_by_project_by_id_code_or_name():
    opening = make_project("opening", "Opening of the shop")
    make_task("In it", project=opening)
    make_task("Outside")
    for data in ({"project_id": str(opening.id)}, {"project": "OPENING"}, {"project": "of the shop"}):
        assert titles(run("task.task.list", data)) == ["In it"], data


def test_filters_by_assignee_and_unassigned(team):
    make_task("Ana's", assigned_to=team["ana"])
    make_task("Bea's", assigned_to=team["worker_member"])
    make_task("Nobody's")
    assert titles(run("task.task.list", {"assigned_to_id": str(team["ana"].id)})) == ["Ana's"]
    assert titles(run("task.task.list", {"assignee": "bea"})) == ["Bea's"]
    assert titles(run("task.task.list", {"unassigned": True})) == ["Nobody's"]


def test_filters_by_parent_top_level_and_tag():
    parent = make_task("Parent", tags=["opening"])
    make_task("Child", parent=parent)
    assert titles(run("task.task.list", {"parent_id": str(parent.id)})) == ["Child"]
    assert titles(run("task.task.list", {"top_level": True})) == ["Parent"]
    assert titles(run("task.task.list", {"tag": "opening"})) == ["Parent"]


def test_filters_by_due_completed_and_created_ranges(today):
    make_task("Early", due_date=dt.date(2026, 10, 1))
    make_task("Late", due_date=dt.date(2026, 10, 31))
    finished = make_task("Finished", status="done", completed_at=timezone.now())
    assert titles(run("task.task.list", {"due_from": "2026-10-15"})) == ["Late"]
    assert titles(run("task.task.list", {"due_to": "2026-10-15"})) == ["Early"]
    assert titles(run("task.task.list", {"completed_from": str(today), "completed_to": str(today)})) == [
        "Finished"
    ]
    assert finished.id in [row.id for row in run("task.task.list", {"created_from": str(today)}).rows]
    assert run("task.task.list", {"created_to": str(today - dt.timedelta(days=1))}).total == 0


def test_the_newest_first_by_default_and_any_column_both_ways(team):
    first = make_task("B first", priority="urgent", due_date=dt.date(2026, 10, 2))
    second = make_task("A second", priority="low")
    third = make_task("C third", priority="high", due_date=dt.date(2026, 10, 1), assigned_to=team["ana"])
    assert [row.id for row in run("task.task.list").rows] == [third.id, second.id, first.id]
    assert titles(run("task.task.list", {"sort": "title"})) == ["A second", "B first", "C third"]
    # Priority by its rank, not by its letters.
    assert titles(run("task.task.list", {"sort": "priority"})) == ["A second", "C third", "B first"]
    assert titles(run("task.task.list", {"sort": "-priority"})) == ["B first", "C third", "A second"]
    # Undated last, both ways.
    assert titles(run("task.task.list", {"sort": "due_date"})) == ["C third", "B first", "A second"]
    assert titles(run("task.task.list", {"sort": "-due_date"})) == ["B first", "C third", "A second"]
    assert titles(run("task.task.list", {"sort": "assignee_name"}))[0] == "C third"


def test_pages():
    for n in range(5):
        make_task(f"T{n}")
    page = run("task.task.list", {"limit": 2, "offset": 2, "sort": "title"})
    assert (titles(page), page.total, page.limit, page.offset) == (["T2", "T3"], 5, 2, 2)


def test_ties_in_the_sorted_column_come_by_id_so_a_touched_row_keeps_its_place_and_pages_add_up():
    """Sorting by a column with repeated values, the row you touched jumped and paging
    repeated or lost rows. Same priority, status and (empty) due date: the id settles every tie, in
    the list's own direction (the next test)."""
    tied = [make_task(f"Tie {n}") for n in range(6)]
    by_id = sorted(task.id for task in tied)
    sorts = ("priority", "-priority", "status", "due_date", "-due_date")

    def listed(sort, **page):
        return [row.id for row in run("task.task.list", {"sort": sort, **page}).rows]

    before = {sort: listed(sort) for sort in sorts}
    # Touching a row makes Postgres write its new version after the others.
    Task.objects.filter(pk=by_id[0]).update(description="touched")
    for sort in sorts:
        assert listed(sort) == before[sort] and sorted(before[sort]) == by_id, sort
    assert before["priority"] == before["status"] == before["due_date"] == by_id
    assert [row for n in (0, 2, 4) for row in listed("priority", limit=2, offset=n)] == by_id


def test_ties_go_by_id_in_the_lists_own_direction():
    """As in Sales, Cash register and Inventory (the old product's rule): a
    descending list settles its ties by id descending, an ascending one ascending — never always ascending."""
    by_id = sorted(make_task(f"Tie {n}").id for n in range(4))

    def listed(sort, **page):
        return [row.id for row in run("task.task.list", {"sort": sort, **page}).rows]

    for column in ("priority", "status", "due_date"):
        assert listed(column) == by_id, column
        assert listed(f"-{column}") == by_id[::-1], f"-{column}"
    assert [row for n in (0, 2) for row in listed("-priority", limit=2, offset=n)] == by_id[::-1]


# My tasks


def test_my_tasks_are_my_open_ones_dated_first_then_the_newest(team, today):
    me = team["worker_member"]
    undated_old = make_task("Undated old", assigned_to=me)
    undated_new = make_task("Undated new", assigned_to=me)
    soon = make_task("Soon", assigned_to=me, due_date=today + dt.timedelta(days=1))
    sooner = make_task("Sooner", assigned_to=me, due_date=today)
    make_task("Done", assigned_to=me, status="done", completed_at=timezone.now())
    make_task("Cancelled", assigned_to=me, status="cancelled")
    make_task("Ana's", assigned_to=team["ana"])
    page = run("task.task.mine", ctx=as_employee(team))
    assert [row.id for row in page.rows] == [sooner.id, soon.id, undated_new.id, undated_old.id]


def test_writing_a_task_does_not_move_its_card_in_my_tasks(team, today):
    """«My tasks» ordered by due date alone, so starting a card sent it to the bottom."""
    me = team["worker_member"]
    for title in ("Oldest", "Middle", "Newest"):
        make_task(title, assigned_to=me)
    make_task("Dated", assigned_to=me, due_date=today)
    ctx = as_employee(team)
    before = titles(run("task.task.mine", ctx=ctx))
    assert before == ["Dated", "Newest", "Middle", "Oldest"]
    for title in ("Oldest", "Middle", "Dated"):
        run("task.task.set_status", {"task": title, "status": "in_progress"}, ctx=ctx)
        run("task.task.update", {"task": title, "priority": "high"}, ctx=ctx)
        run("task.comment.add", {"task": title, "text": "On it"}, ctx=ctx)
        assert titles(run("task.task.mine", ctx=ctx)) == before


def test_my_tasks_within_a_horizon_leave_the_undated_out(team, today):
    me = team["worker_member"]
    make_task("This week", assigned_to=me, due_date=today + dt.timedelta(days=6))
    make_task("Next month", assigned_to=me, due_date=today + dt.timedelta(days=30))
    make_task("Undated", assigned_to=me)
    assert titles(run("task.task.mine", {"due_within_days": 7}, ctx=as_employee(team))) == ["This week"]


def test_without_a_staff_record_my_tasks_are_empty(make_user):
    lone = make_user("lone", role="hub_employee")
    make_task()
    assert run("task.task.mine", ctx=ctx_for("hub_employee", actor=lone)).total == 0


# Subtasks


def test_subtasks_in_the_order_they_were_added():
    parent = make_task("Parent")
    first = make_task("First", parent=parent)
    second = make_task("Second", parent=parent)
    make_task("Grandchild", parent=first)
    page = run("task.task.subtasks", {"id": str(parent.id)})
    assert [row.id for row in page.rows] == [first.id, second.id]


def test_an_employee_reads_only_their_own_subtasks(team):
    parent = make_task("Parent", assigned_to=team["worker_member"])
    make_task("Mine too", parent=parent, assigned_to=team["worker_member"])
    make_task("Ana's", parent=parent, assigned_to=team["ana"])
    assert titles(run("task.task.subtasks", {"id": str(parent.id)}, ctx=as_employee(team))) == ["Mine too"]


# Nothing of a task the caller does not see leaks through a row of one they do see


def test_an_employee_reads_nothing_of_a_parent_they_do_not_see(team):
    parent = make_task("Boss's secret", number="TSK-20261014-0099", assigned_to=team["ana"])
    child = make_task("Mine", parent=parent, assigned_to=team["worker_member"])
    row = run("task.task.detail", {"id": str(child.id)}, ctx=as_employee(team))
    assert (row.parent_number, row.parent_title) == (None, None)
    [listed] = run("task.task.list", ctx=as_employee(team)).rows
    assert (listed.parent_number, listed.parent_title) == (None, None)
    # Positive control: the manager sees the parent.
    row = run("task.task.detail", {"id": str(child.id)}, ctx=as_manager(team))
    assert (row.parent_number, row.parent_title) == ("TSK-20261014-0099", "Boss's secret")


def test_a_parent_the_employee_sees_is_named(team):
    parent = make_task("My parent", number="TSK-20261014-0098", created_by=team["worker"].person)
    child = make_task("Mine", parent=parent, assigned_to=team["worker_member"])
    assert run("task.task.detail", {"id": str(child.id)}, ctx=as_employee(team)).parent_title == "My parent"


def test_the_counts_only_count_what_the_caller_sees(team):
    project = make_project()
    parent = make_task("Mine", project=project, assigned_to=team["worker_member"])
    make_task("Mine too", parent=parent, assigned_to=team["worker_member"])
    make_task("Ana's", parent=parent, project=project, assigned_to=team["ana"])
    make_task("Ana's done", project=project, assigned_to=team["ana"], status="done", completed_at=timezone.now())
    assert run("task.task.detail", {"id": str(parent.id)}, ctx=as_employee(team)).subtask_count == 1
    assert run("task.task.detail", {"id": str(parent.id)}, ctx=as_manager(team)).subtask_count == 2
    [mine] = run("task.project.list", ctx=as_employee(team)).rows
    assert (mine.task_count, mine.open_task_count) == (1, 1)
    assert run("task.project.detail", {"id": str(project.id)}, ctx=as_employee(team)).task_count == 1
    [everything] = run("task.project.list", ctx=as_manager(team)).rows
    assert (everything.task_count, everything.open_task_count) == (3, 2)
