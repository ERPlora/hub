"""Read operations of the task app: what each one returns, who sees what (an employee, their own
tasks; a manager, every task), how a task and a project are named, and the lists' filters and sorts."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.task.models import Task

from .conftest import ctx_for, make_comment, make_member, make_project, make_task

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def run(name, data=None, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def titles(page):
    return [row.title for row in page.rows]


@pytest.fixture
def team(make_user):
    """A manager and an employee with their staff records linked, and a third person without account."""
    boss = make_user("boss", role="hub_manager", first_name="Marta", last_name="Jefa")
    worker = make_user("bea", role="hub_employee", first_name="Bea", last_name="Ruiz")
    return {
        "boss": boss,
        "worker": worker,
        "boss_member": make_member("Marta", "Jefa", user=boss),
        "worker_member": make_member("Bea", "Ruiz", user=worker),
        "ana": make_member("Ana", "López"),
    }


def as_employee(team):
    return ctx_for("hub_employee", actor=team["worker"])


def as_manager(team):
    return ctx_for("hub_manager", actor=team["boss"])


# Who sees what


def test_a_manager_sees_every_task_and_an_employee_their_own(team):
    make_task("Mine by assignment", assigned_to=team["worker_member"])
    make_task("Mine by creation", created_by=team["worker"], assigned_to=team["ana"])
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
    make_task("Created by me", created_by=lone)
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


# A row


def test_a_row_carries_its_project_parent_assignee_creator_and_counts(team):
    project = make_project("opening", "Opening", color="#AA3300")
    parent = make_task("Opening prep", number="TSK-20261014-0001", project=project)
    task = make_task(
        "Buy towels",
        project=project,
        parent=parent,
        assigned_to=team["ana"],
        created_by=team["boss"],
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
        team["boss"].pk,
    )
    assert (row.subtask_count, row.comment_count, row.tags, row.due_date) == (
        1,
        2,
        ["stock"],
        dt.date(2026, 10, 20),
    )


def test_a_creator_without_a_name_reads_as_their_email_or_username(make_user):
    plain = make_user("plain")
    task = make_task(created_by=plain)
    assert run("task.task.detail", {"id": str(task.id)}).created_by_name == "plain"


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


def test_overdue_is_open_and_due_before_the_business_today():
    yesterday = TODAY - dt.timedelta(days=1)
    make_task("Late", due_date=yesterday)
    make_task("Today", due_date=TODAY)
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


def test_filters_by_due_completed_and_created_ranges():
    make_task("Early", due_date=dt.date(2026, 10, 1))
    make_task("Late", due_date=dt.date(2026, 10, 31))
    finished = make_task("Finished", status="done", completed_at=timezone.now())
    assert titles(run("task.task.list", {"due_from": "2026-10-15"})) == ["Late"]
    assert titles(run("task.task.list", {"due_to": "2026-10-15"})) == ["Early"]
    assert titles(run("task.task.list", {"completed_from": str(TODAY), "completed_to": str(TODAY)})) == [
        "Finished"
    ]
    assert finished.id in [row.id for row in run("task.task.list", {"created_from": str(TODAY)}).rows]
    assert run("task.task.list", {"created_to": str(TODAY - dt.timedelta(days=1))}).total == 0


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
    """hub#2352: sorting by a column with repeated values, the row you touched jumped and paging
    repeated or lost rows. Same priority, status and (empty) due date: the id settles every tie. Which
    way on a descending sort is not pinned: the old product's rule (the list's own direction) and
    ``_sorted`` (always ascending) differ, flagged in the CLOSE-TASK round of PLAN-HUB."""
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


# My tasks


def test_my_tasks_are_my_open_ones_dated_first_then_the_newest(team):
    me = team["worker_member"]
    undated_old = make_task("Undated old", assigned_to=me)
    undated_new = make_task("Undated new", assigned_to=me)
    soon = make_task("Soon", assigned_to=me, due_date=TODAY + dt.timedelta(days=1))
    sooner = make_task("Sooner", assigned_to=me, due_date=TODAY)
    make_task("Done", assigned_to=me, status="done", completed_at=timezone.now())
    make_task("Cancelled", assigned_to=me, status="cancelled")
    make_task("Ana's", assigned_to=team["ana"])
    page = run("task.task.mine", ctx=as_employee(team))
    assert [row.id for row in page.rows] == [sooner.id, soon.id, undated_new.id, undated_old.id]


def test_writing_a_task_does_not_move_its_card_in_my_tasks(team):
    """tasks#45: «My tasks» ordered by due date alone, so starting a card sent it to the bottom."""
    me = team["worker_member"]
    for title in ("Oldest", "Middle", "Newest"):
        make_task(title, assigned_to=me)
    make_task("Dated", assigned_to=me, due_date=TODAY)
    ctx = as_employee(team)
    before = titles(run("task.task.mine", ctx=ctx))
    assert before == ["Dated", "Newest", "Middle", "Oldest"]
    for title in ("Oldest", "Middle", "Dated"):
        run("task.task.set_status", {"task": title, "status": "in_progress"}, ctx=ctx)
        run("task.task.update", {"task": title, "priority": "high"}, ctx=ctx)
        run("task.comment.add", {"task": title, "text": "On it"}, ctx=ctx)
        assert titles(run("task.task.mine", ctx=ctx)) == before


def test_my_tasks_within_a_horizon_leave_the_undated_out(team):
    me = team["worker_member"]
    make_task("This week", assigned_to=me, due_date=TODAY + dt.timedelta(days=6))
    make_task("Next month", assigned_to=me, due_date=TODAY + dt.timedelta(days=30))
    make_task("Undated", assigned_to=me)
    assert titles(run("task.task.mine", {"due_within_days": 7}, ctx=as_employee(team))) == ["This week"]


def test_without_a_staff_record_my_tasks_are_empty(make_user):
    lone = make_user("lone", role="hub_employee")
    make_task()
    assert run("task.task.mine", ctx=ctx_for("hub_employee", actor=lone)).total == 0


# Subtasks and comments


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


def test_comments_newest_first_with_their_author(team):
    task = make_task()
    make_comment(task, "First", author=team["boss"])
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


# Projects


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
    parent = make_task("My parent", number="TSK-20261014-0098", created_by=team["worker"])
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
