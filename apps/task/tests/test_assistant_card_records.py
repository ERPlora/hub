"""The card of a write of Tasks (hub#677) says which task, project or person it acts on by its name, read as whoever
asks, never by its id, and leaves it out when that person may not read it or it is not there. A task goes by its title
(what the person says of it: «complete the task clean the store room»), a project by its name, as the screens' «Delete»
dialog says it, and a person of the team by their full name, as Staff names them.
"""

import dataclasses

import pytest
from live.context import OperationContext, Scope
from live.operations import get

from apps.task.tests.conftest import A, ctx_for, make_member, make_project, make_task
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

#: Each write of Tasks and the datum of it that names a task by its id.
ON_A_TASK = [
    ("task.comment.add", "task_id"),
    ("task.task.assign", "id"),
    ("task.task.complete", "id"),
    ("task.task.create", "parent_id"),
    ("task.task.delete", "id"),
    ("task.task.set_status", "id"),
    ("task.task.update", "id"),
]
#: Each one that names a project by its id.
ON_A_PROJECT = [
    ("task.project.delete", "id"),
    ("task.project.update", "id"),
    ("task.task.create", "project_id"),
    ("task.task.update", "project_id"),
]
#: Each one that names a person of the team (Staff) by their id.
ON_A_PERSON = [
    ("task.project.create", "owner_id"),
    ("task.project.update", "owner_id"),
    ("task.task.assign", "member_id"),
    ("task.task.create", "assigned_to_id"),
]


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for())
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A task by its title, a project by its name, a person by their full name ───────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_TASK)
def test_a_write_on_a_task_says_it_by_its_title(write, datum):
    """The case the issue names, «task.comment.add:task_id»: «Task: Clean the store room», never its id."""
    task = make_task("Clean the store room")
    assert shown(write, {datum: str(task.id)})[datum] == "Clean the store room"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PROJECT)
def test_a_write_on_a_project_says_it_by_its_name(write, datum):
    project = make_project("q3-audit", "Q3 audit")
    assert shown(write, {datum: str(project.id)})[datum] == "Q3 audit"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PERSON)
def test_a_write_on_a_person_says_them_by_their_full_name(write, datum):
    ana = make_member("Ana", "López")
    assert shown(write, {datum: str(ana.id)})[datum] == "Ana López"


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "title"), [("en", "Task"), ("es", "Tarea")])
def test_the_case_of_the_issue_reads_task_and_its_title_in_each_language(language, title):
    task = make_task("Limpiar el almacén")
    field = fields_of("task.comment.add", {"task_id": str(task.id), "text": "Hecho"}, language)["task_id"]
    assert (field["value"], field["label"]) == ("Limpiar el almacén", title)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own record, never another of the list (the first, the last, the one of the same project)."""
    project = make_project("opening", "Opening")
    tasks = [make_task("Order the chairs", project=project), make_task("Paint the walls", project=project)]
    projects = [project, make_project("q3-audit", "Q3 audit")]
    people = [make_member("Ana", "López"), make_member("Bea", "Ruiz")]
    for listed in (tasks, list(reversed(tasks))):
        assert [shown("task.task.complete", {"id": str(task.id)})["id"] for task in listed] == [t.title for t in listed]
    for listed in (projects, list(reversed(projects))):
        assert [shown("task.project.delete", {"id": str(p.id)})["id"] for p in listed] == [p.name for p in listed]
    for listed in (people, list(reversed(people))):
        arguments = [{"id": str(tasks[0].id), "member_id": str(member.id)} for member in listed]
        said = [shown("task.task.assign", each)["member_id"] for each in arguments]
        assert said == [f"{m.first_name} {m.last_name}" for m in listed]


@pytest.mark.django_db
def test_a_change_keeps_saying_the_record_beside_what_it_changes():
    """The name is the record's as it is now, before the write runs: a rename says the old title under «Task» and the
    new one under its own datum; a project moved says the task, the project it goes to and nothing by an id."""
    task = make_task("Clean the store room")
    project = make_project("opening", "Opening")
    arguments = {"id": str(task.id), "title": "Tidy the store room", "project_id": str(project.id)}
    said = shown("task.task.update", arguments)
    assert said == {"id": "Clean the store room", "title": "Tidy the store room", "project_id": "Opening"}
    renamed = shown("task.project.update", {"id": str(project.id), "name": "Grand opening"})
    assert renamed == {"id": "Opening", "name": "Grand opening"}


@pytest.mark.django_db
def test_a_new_subtask_says_the_task_it_hangs_from_and_whom_it_goes_to():
    parent = make_task("Open the shop")
    ana = make_member("Ana", "López")
    arguments = {"title": "Order the chairs", "parent_id": str(parent.id), "assigned_to_id": str(ana.id)}
    said = shown("task.task.create", arguments)
    assert said == {"title": "Order the chairs", "parent_id": "Open the shop", "assigned_to_id": "Ana López"}


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_TASK + ON_A_PROJECT)
def test_what_the_person_may_not_read_is_left_out_never_said_by_its_id(write, datum):
    """Whoever may not see the tasks (``task.view``) is told no task nor project."""
    record = make_project() if (write, datum) in ON_A_PROJECT else make_task()
    arguments = {datum: str(record.id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("task.view"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PERSON)
def test_a_person_is_left_out_for_whoever_may_not_see_the_team(write, datum):
    """A person of the team is Staff's to name (``staff.view``): without it, the card says nobody."""
    ana = make_member("Ana", "López")
    arguments = {datum: str(ana.id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("staff.view"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_task_an_employee_does_not_see_is_left_out_for_them(make_user):
    """An employee sees the tasks assigned to them or made by them: another person's task is not theirs to read, so
    the card does not name it to them, as the list does not show it."""
    bea = make_user("bea", role="hub_employee", first_name="Bea", last_name="Ruiz")
    mine = make_task("Mine", assigned_to=make_member("Bea", "Ruiz", user=bea.person))
    others = make_task("Ana's", assigned_to=make_member("Ana", "López"))
    employee = ctx_for("hub_employee", actor=bea)
    assert shown("task.comment.add", {"task_id": str(mine.id)}, ctx=employee) == {"task_id": "Mine"}
    assert shown("task.comment.add", {"task_id": str(others.id)}, ctx=employee) == {}
    assert shown("task.comment.add", {"task_id": str(others.id)}) == {"task_id": "Ana's"}  # an admin sees it


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_TASK + ON_A_PROJECT + ON_A_PERSON)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_record_deleted_meanwhile_is_left_out():
    task = make_task("Clean the store room")
    arguments = {"id": str(task.id)}
    assert shown("task.task.delete", arguments) == {"id": "Clean the store room"}  # positive control
    task.delete()
    assert shown("task.task.delete", arguments) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    task = make_task("Clean the store room")
    card = assistant.card(get("task.task.update"), {"id": str(task.id), "title": "Tidy"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"title": "Tidy"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        records = [
            ("task.task.delete", "id", make_task("Clean the store room")),
            ("task.project.delete", "id", make_project("opening", "Opening")),
            ("task.task.assign", "member_id", make_member("Ana", "López")),
        ]
        for write, datum, record in records:  # positive control
            assert datum in shown(write, {datum: str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, datum, record in records:
            assert datum not in shown(write, {datum: str(record.id)}, ctx=in_b), write
