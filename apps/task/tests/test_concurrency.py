"""Two people at once: real sessions in threads, real row locks (WORKBOOK «Para quien lo mantiene»).

Two tasks created at the same moment get consecutive numbers, never the same one; two completions of
the same task close it once and the second one is told it was already closed. A task or a project given
to a person the Hub admin is deleting at that moment is never a 500, and neither is a task or a project
deleted while it is being shown or changed.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import RequestFactory
from django.utils import timezone
from live.errors import OperationError
from live.models import OutboxEvent
from live.operations import get

from apps.staff.models import Member
from apps.task import events
from apps.task.models import Project, Task
from apps.task.queries import PROJECT_NOT_FOUND, TASK_NOT_FOUND

from .conftest import ctx_for, make_member, make_project, make_task

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # an expected refusal or an unexpected failure, both reported
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_tasks_created_at_once_get_consecutive_numbers():
    results = at_once(*(lambda n=n: run("task.task.create", {"title": f"T{n}"}) for n in range(4)))
    day = timezone.localdate().strftime("%Y%m%d")
    assert sorted(result.number for result in results) == [f"TSK-{day}-{n:04d}" for n in range(1, 5)]


def test_two_completions_of_the_same_task_close_it_once():
    task = make_task()
    results = at_once(*(lambda: run("task.task.complete", {"id": str(task.id)}) for _ in range(2)))
    refused = [result for result in results if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "task.task_already_closed"
    assert Task.objects.get(pk=task.pk).status == "done"
    assert OutboxEvent.objects.filter(name="task.task.completed").count() == 1


# ── The Hub admin's «Delete» of a person ─────────────────────────────────────────────────────────
#
# A task's assignee and a project's owner are staff records. The Hub admin's «Delete» of a record enters
# through it (staff's ``lock_members``), clears the tasks and projects that name it and then deletes it. A
# write that read the person without holding her named her after that deletion had committed: the reference
# was refused at the write's COMMIT (a 500). A write holds the person before its task or project, in the
# order the deletion takes them: the deletion waits for the write and then clears what it left, or the
# write waits for the deletion and hears she is gone, as for a person deleted before.

#: How long the deletion runs on its own before the write goes on: long enough to reach the record.
IN_FLIGHT = 0.5
ADMIN_DELETIONS = ["delete_model", "delete_queryset"]


def admin_delete(target, how: str) -> None:
    """The Hub admin's «Delete» of ``target`` (a person, a task or a project): its page (``delete_model``)
    or the list's «Delete selected» action (``delete_queryset``), as the staff run them."""
    model = type(target)
    model_admin = admin.site._registry[model]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, model.objects.filter(pk=target.pk))
    else:
        model_admin.delete_model(request, model.objects.get(pk=target.pk))


@contextmanager
def admin_deleting(member: Member, how: str, after: Callable[[str], bool]):
    """The Hub admin's «Delete» of ``member`` started in another session right before the first statement
    of this one for which ``after`` holds, and left to run a moment before this one goes on."""
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                admin_delete(member, how)
            deletions.append("ok")
        except Exception as error:  # a deadlock, reported to the test
            deletions.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and after(sql):
            thread.start()
            time.sleep(IN_FLIGHT)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "the deletion never started"


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def attempt(call):
    """What ``call`` answers: its result, or the error it is refused with (a 500 is raised as it comes)."""
    try:
        return call()
    except OperationError as error:
        return error


def starts(statement: str) -> Callable[[str], bool]:
    return lambda sql: sql.lstrip().startswith(statement)


def reads_a_person(sql: str) -> bool:
    return sql.lstrip().startswith("SELECT") and 'FROM "staff_member"' in sql


def taking_it_herself(ana: Member, task: Task):
    """«Assign to me» by Ana herself: a user of the hub with her staff record."""
    user = get_user_model().objects.create_user(username="ana", password="pw")
    Member.objects.filter(pk=ana.pk).update(user=user)
    op = get("task.task.assign")
    return lambda: op(ctx_for("hub_admin", actor=user), op.input.model_validate({"id": str(task.id), "to_me": True}))


def new_task(_ana):
    return make_task()


def new_project(_ana):
    return make_project()


#: What names Ana while the admin deletes her: the row it needs, the call, the write's statement that
#: names her (the deletion starts right before it) and the row the write left.
WRITTEN_NAMING_A_PERSON = {
    "creating a task for her": (
        lambda ana: None,
        lambda ana, row: lambda: run("task.task.create", {"title": "Count the till", "assigned_to_id": str(ana.id)}),
        starts('INSERT INTO "task_task"'),
        lambda row: Task.objects.get(title="Count the till").assigned_to_id,
    ),
    "creating a task for her by name": (
        lambda ana: None,
        lambda ana, row: lambda: run("task.task.create", {"title": "Count the till", "assignee": "Ana López"}),
        starts('INSERT INTO "task_task"'),
        lambda row: Task.objects.get(title="Count the till").assigned_to_id,
    ),
    "assigning her a task": (
        new_task,
        lambda ana, row: lambda: run("task.task.assign", {"id": str(row.id), "member_id": str(ana.id)}),
        starts('UPDATE "task_task"'),
        lambda row: Task.objects.get(pk=row.pk).assigned_to_id,
    ),
    "assigning her a task by name": (
        new_task,
        lambda ana, row: lambda: run("task.task.assign", {"id": str(row.id), "member": "Ana López"}),
        starts('UPDATE "task_task"'),
        lambda row: Task.objects.get(pk=row.pk).assigned_to_id,
    ),
    "her taking a task herself": (
        new_task,
        taking_it_herself,
        starts('UPDATE "task_task"'),
        lambda row: Task.objects.get(pk=row.pk).assigned_to_id,
    ),
    "making her a project's owner": (
        lambda ana: None,
        lambda ana, row: lambda: run("task.project.create", {"code": "spring", "name": "Spring", "owner_id": str(ana.id)}),
        starts('INSERT INTO "task_project"'),
        lambda row: Project.objects.get(code="spring").owner_id,
    ),
    "making her a project's owner by name": (
        lambda ana: None,
        lambda ana, row: lambda: run("task.project.create", {"code": "spring", "name": "Spring", "owner": "Ana López"}),
        starts('INSERT INTO "task_project"'),
        lambda row: Project.objects.get(code="spring").owner_id,
    ),
    "handing her a project": (
        new_project,
        lambda ana, row: lambda: run("task.project.update", {"id": str(row.id), "owner_id": str(ana.id)}),
        starts('UPDATE "task_project"'),
        lambda row: Project.objects.get(pk=row.pk).owner_id,
    ),
    "handing her a project by name": (
        new_project,
        lambda ana, row: lambda: run("task.project.update", {"id": str(row.id), "owner": "Ana López"}),
        starts('UPDATE "task_project"'),
        lambda row: Project.objects.get(pk=row.pk).owner_id,
    ),
}


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
@pytest.mark.parametrize("written", sorted(WRITTEN_NAMING_A_PERSON))
def test_a_write_naming_a_person_the_hub_admin_deletes_meanwhile_is_waited_for(written, how):
    setup, call, after, left = WRITTEN_NAMING_A_PERSON[written]
    ana = make_member()
    row = setup(ana)
    write = call(ana, row)
    with admin_deleting(ana, how, after) as deletions:
        outcome = attempt(write)
    # The deletion waited for the write, which went through, and then cleared what the write left.
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert not Member.objects.filter(pk=ana.pk).exists()
    assert left(row) is None


#: A write on a task or project that already names Ana, naming her again while the admin deletes her: the
#: row, the call, the field it names her with and the row's reference to her.
WRITTEN_ON_A_ROW_OF_A_PERSON = {
    "assigning her task to her again": (
        lambda ana: make_task(assigned_to=ana),
        lambda ana, row: run("task.task.assign", {"id": str(row.id), "member_id": str(ana.id)}),
        "member_id",
        lambda row: Task.objects.get(pk=row.pk).assigned_to_id,
    ),
    "handing her project to her again": (
        lambda ana: make_project(owner=ana),
        lambda ana, row: run("task.project.update", {"id": str(row.id), "name": "Spring", "owner_id": str(ana.id)}),
        "owner_id",
        lambda row: Project.objects.get(pk=row.pk).owner_id,
    ),
}


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
@pytest.mark.parametrize("written", sorted(WRITTEN_ON_A_ROW_OF_A_PERSON))
def test_a_write_on_a_row_of_a_person_the_hub_admin_is_deleting_never_waits_in_a_circle(written, how):
    # The deletion holds her and then clears the task or project that names her. A write that held that row
    # and then went for her waited for the deletion while the deletion waited for it. Holding her first, the
    # write waits for the deletion and hears she is gone, on the field that named her.
    setup, call, field, left = WRITTEN_ON_A_ROW_OF_A_PERSON[written]
    ana = make_member()
    row = setup(ana)
    with admin_deleting(ana, how, reads_a_person) as deletions:
        outcome = attempt(lambda: call(ana, row))
    assert deleted(deletions) == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields)) == (422, "invalid_field", [field])
    assert not Member.objects.filter(pk=ana.pk).exists()
    assert left(row) is None


# ── A task or a project deleted while it is read ─────────────────────────────────────────────────
#
# The detail of a task or a project found it and then loaded it again by its id, and a command found it and
# then locked it by its id: a deletion committed between the two reads (the business's «Delete» or the Hub
# admin's) raised DoesNotExist, a 500. The detail is read once, as it was; the command hears it is gone.

#: Who takes a task or a project away: the business's «Delete» and the Hub admin's two.
DELETIONS = ["operation", *ADMIN_DELETIONS]
DELETE_OPERATION = {Task: "task.task.delete", Project: "task.project.delete"}
DELETED_EVENT = {Task: events.TASK_DELETED, Project: events.PROJECT_DELETED}


def delete(target, how: str) -> None:
    if how == "operation":
        run(DELETE_OPERATION[type(target)], {"id": str(target.pk)})
    else:
        with transaction.atomic():
            admin_delete(target, how)


@contextmanager
def deleted_once_found(target, how: str):
    """Commits the deletion of ``target`` in another session right after the first statement of this one
    that reads its table and finds a row (the read that found it): every time between that read and the
    next one."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        found = sql.lstrip().upper().startswith("SELECT") and table in sql and context["cursor"].rowcount > 0
        if not deletions and found:
            deletions.extend(at_once(lambda: delete(target, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def a_task():
    return make_task("Clean the store room")


def a_project():
    return make_project(code="OPN", name="Opening")


#: Each detail: the row it shows, the reference it is named by and the fields that show it is that row.
DETAILS = {
    "a task by its id": (a_task, "task.task.detail", lambda row: {"id": str(row.pk)}, ("number", "title")),
    "a task by its number": (a_task, "task.task.detail", lambda row: {"task": row.number}, ("number", "title")),
    "a task by its title": (a_task, "task.task.detail", lambda row: {"task": row.title}, ("number", "title")),
    "a project by its id": (a_project, "task.project.detail", lambda row: {"id": str(row.pk)}, ("code", "name")),
    "a project by its code": (a_project, "task.project.detail", lambda row: {"project": row.code}, ("code", "name")),
    "a project by its name": (a_project, "task.project.detail", lambda row: {"project": row.name}, ("code", "name")),
}
NOT_FOUND = {Task: TASK_NOT_FOUND, Project: PROJECT_NOT_FOUND}


def gone(row, outcome) -> None:
    """``outcome`` is the app's own 404 for ``row``: its code and its message, never a 500."""
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, outcome.message) == (404, "not_found", str(NOT_FOUND[type(row)]))


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("shown", sorted(DETAILS))
def test_a_task_or_project_deleted_while_its_detail_is_read_is_shown_as_it_was(shown, how):
    setup, detail, named, fields = DETAILS[shown]
    row = setup()
    with deleted_once_found(row, how) as deletions:
        outcome = attempt(lambda: run(detail, named(row)))
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert (outcome.id, *(getattr(outcome, field) for field in fields)) == (
        row.pk,
        *(getattr(row, field) for field in fields),
    )
    # What the deletion's event runs next: not found, and the open sheet closes.
    gone(row, attempt(lambda: run(detail, named(row))))


#: Each command on a task or a project: the row it changes and what it is sent.
CHANGED = {
    "editing a task": (a_task, "task.task.update", lambda row: {"id": str(row.pk), "title": "Sweep the store room"}),
    "moving a task on": (a_task, "task.task.set_status", lambda row: {"id": str(row.pk), "status": "in_progress"}),
    "completing a task": (a_task, "task.task.complete", lambda row: {"id": str(row.pk)}),
    "unassigning a task": (a_task, "task.task.assign", lambda row: {"id": str(row.pk)}),
    "commenting on a task": (a_task, "task.comment.add", lambda row: {"task_id": str(row.pk), "text": "On it"}),
    "deleting a task": (a_task, "task.task.delete", lambda row: {"id": str(row.pk)}),
    "editing a project": (a_project, "task.project.update", lambda row: {"id": str(row.pk), "name": "Grand opening"}),
    "deleting a project": (a_project, "task.project.delete", lambda row: {"id": str(row.pk)}),
}


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("changed", sorted(CHANGED))
def test_a_task_or_project_deleted_while_a_command_finds_it_is_not_found(changed, how):
    # Twice «Delete» at once included: the second one hears it is gone, as a deletion committed before.
    setup, command, sent = CHANGED[changed]
    row = setup()
    with deleted_once_found(row, how) as deletions:
        outcome = attempt(lambda: run(command, sent(row)))
    assert deleted(deletions) == ["ok"]
    gone(row, outcome)
    assert not type(row).objects.filter(pk=row.pk).exists()
    # Nothing of the refused command is left: only the deletion's own event, if it records one.
    recorded = list(OutboxEvent.objects.values_list("name", flat=True))
    assert recorded == ([DELETED_EVENT[type(row)]] if how == "operation" else []), recorded
