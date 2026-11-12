"""hub#1208 and hub#1219 in Tasks: the yes to the card of a task said by its name touches only what that card showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). In Tasks a task is
found by its number or its title alone (``resolve_task``) and a project by its code or its name alone
(``resolve_project``): a write that takes one by its name reads it on its card by that name, as the write will find it
(``names(…, by="task")``, ``names(…, by="project")``), and checks it before any card (``check``). The card says the task
or the project it found («Llamar al proveedor» when the person said «llamar»), a name two fit or none has draws no
card, and a yes after another one fits the name better runs nothing and shows the new card, as Demo (hub#1206), Menus
(hub#1217) and Modifiers (hub#1218) do (TASK-F05 to TASK-F08, TASK-F11, TASK-F13, TASK-F14, BASE-F97).
"""

import dataclasses
import json

import pytest
from live.operations import get, registry

from apps.task.models import Comment, Project, Task
from apps.task.tests.conftest import ctx_for, make_member, make_project, make_task
from apps.task.tests.test_integration_assistant import SCREENS, SCREENS_EN, task_writes
from base import assistant
from base.schemas import names
from base.tests.test_assistant_yes_for_its_card import turn_as, yes_to_its_card
from base.tests.test_services_assistant import call

pytestmark = pytest.mark.django_db

BY_ITS_NAME = ("task.task.delete", {"task": "llamar"})

#: The writes of Tasks that take a task by its name (``TaskRefIn``), each checked with the task's read before its card.
ON_A_TASK = ("task.task.assign", "task.task.complete", "task.task.delete", "task.task.set_status", "task.task.update")
#: The writes that take a project by its name (``ProjectRefIn``), each checked with the project's read.
ON_A_PROJECT = ("task.project.delete", "task.project.update")
CHECKS = {
    **dict.fromkeys(ON_A_TASK, "task.task.detail"),
    **dict.fromkeys(ON_A_PROJECT, "task.project.detail"),
}
#: Each write that takes a task or a project by its name with no read whose input fits theirs to check it with
#: (``base.E012``: the task's and the project's reads take an ``id`` that is the write's own record or none): their
#: card reads them by that name all the same, so the yes holds to what it found, and says them as said when two fit
#: (hub#1245). The data: a task commented on, a new task's project and parent task, and the project a task is moved to.
UNCHECKED = {
    "task.comment.add": ("task",),
    "task.task.create": ("parent", "project"),
    "task.task.update": ("project",),
}


def by_its_name(said: str) -> dict[str, dict]:
    """The data of each write that takes its task (``ON_A_TASK``) or its project (``ON_A_PROJECT``) by its name, with
    that task or project said as ``said``."""
    member = make_member("Ana", "López")
    return {
        "task.task.assign": {"task": said, "member_id": str(member.id)},
        "task.task.complete": {"task": said},
        "task.task.delete": {"task": said},
        "task.task.set_status": {"task": said, "status": "in_progress"},
        "task.task.update": {"task": said, "priority": "urgent"},
        "task.project.delete": {"project": said},
        "task.project.update": {"project": said, "color": "#AA3300"},
    }


def two(write: str) -> tuple[str, str, object]:
    """What ``write`` acts on: its datum, the name the card shows for the one that fits «llamar» or «apertura», and how
    to make another one with ``name``."""
    if write in ON_A_PROJECT:
        return "project", "Apertura del local", lambda name: make_project(_code(name), name)
    return "task", "Llamar al proveedor", lambda name: make_task(name)


def _code(name: str) -> str:
    return "p-" + name.lower().replace(" ", "-")[:20]


def said(write: str) -> str:
    return "apertura" if write in ON_A_PROJECT else "llamar"


def as_admin(language: str = "es"):
    return dataclasses.replace(ctx_for("hub_admin"), language=language)


def one(language: str, write: str) -> str:
    """What the list of tasks or of projects calls one, as the card titles it («Tarea», «Project»)."""
    screens = {"es": SCREENS, "en": SCREENS_EN}[language]
    word = screens["projects" if write in ON_A_PROJECT else "tasks"]["entity"]["one"]
    return word[:1].upper() + word[1:]


def on_card(plan: dict, datum: str) -> list[tuple[str, object]]:
    return [(field["name"], field["value"]) for field in plan["confirm"]["fields"] if field["name"] == datum]


def fields_of(write: str, arguments: dict, language: str = "es") -> dict:
    card = assistant.card(get(write), arguments, language, as_admin(language))
    return {field["name"]: field for field in card["fields"]}


def state() -> tuple:
    """Every task, comment and project, with what the writes here change."""
    return (
        sorted(
            Task.objects.values_list("title", "status", "priority", "assigned_to_id", "project__name", "parent__title")
        ),
        sorted(Comment.objects.values_list("task__title", "text")),
        sorted(Project.objects.values_list("name", "color")),
    )


def yes_after_another_comes(write: str, arguments: dict) -> tuple[dict, tuple]:
    """``write`` asked for with ``arguments`` while only one task or project fits its name; somebody creates one whose
    name is exactly what was said before the yes. → the yes's turn, and everything as it was just before it."""
    datum, _, make = two(write)
    make("Apertura del local" if datum == "project" else "Llamar al proveedor")
    before = {}

    def meanwhile():
        make(said(write).capitalize())
        before["state"] = state()

    done = yes_to_its_card(as_admin(), write, arguments, meanwhile=meanwhile)
    return done, before["state"]


def test_the_yes_to_the_card_of_a_task_said_by_its_name_runs_on_it():
    """Control: nothing changed between the card and the yes."""
    shown = make_task("Llamar al proveedor")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert not Task.objects.filter(pk=shown.pk).exists()


def test_the_yes_touches_only_the_task_its_card_showed_although_another_fits_the_name_better_meanwhile():
    """The case of the issue: «borra la tarea llamar» shows «Llamar al proveedor»; somebody creates «Llamar» before
    the yes (the same title wins over one that holds it): the yes deletes neither, and the card now says «Llamar»."""
    make_task("Llamar al proveedor")
    assert on_card(turn_as(as_admin(), call(*BY_ITS_NAME)), "task") == [("task", "Llamar al proveedor")]

    done = yes_to_its_card(as_admin(), *BY_ITS_NAME, meanwhile=lambda: make_task("Llamar"))

    assert done["executed"] == []
    assert on_card(done, "task") == [("task", "Llamar")]
    assert sorted(Task.objects.values_list("title", flat=True)) == ["Llamar", "Llamar al proveedor"]


@pytest.mark.parametrize("write", sorted(CHECKS))
def test_a_write_on_a_record_said_by_its_name_says_the_one_it_finds(write):
    """The card reads the task or the project by what was said, as the write will find it: its own title or name, even
    when only part of it was said, under the word its list calls one («Tarea: Llamar al proveedor»), never the words
    said («llamar»)."""
    datum, found, make = two(write)
    make(found)
    make("Pedir hielo" if datum == "task" else "Reforma del baño")
    for language in ("es", "en"):
        field = fields_of(write, by_its_name(said(write))[write], language)[datum]
        assert (field["value"], field["label"]) == (found, one(language, write)), (write, language)


@pytest.mark.parametrize("write", sorted(CHECKS))
def test_the_yes_runs_nothing_when_another_record_fits_the_name_better_before_it(write):
    """«llamar» shows «Llamar al proveedor»; somebody creates «Llamar» before the yes (or «Apertura» for «apertura»):
    the yes runs nothing on either, and the card it shows now says the new one."""
    datum = two(write)[0]
    done, before = yes_after_another_comes(write, by_its_name(said(write))[write])
    assert done["executed"] == []
    assert on_card(done, datum) == [(datum, said(write).capitalize())]
    assert state() == before


@pytest.mark.parametrize("write", sorted(CHECKS))
def test_a_name_two_records_fit_draws_no_card_and_the_model_hears_it(write):
    """«llamar» fits «Llamar al proveedor» and «Llamar al gestor»: no card that would act on either; the model hears
    the ambiguity and asks the person which one (BASE-G115: the data are checked before any card)."""
    datum, found, make = two(write)
    make(found)
    make("Llamar al gestor" if datum == "task" else "Apertura de la terraza")
    code = "task.ambiguous_project" if datum == "project" else "task.ambiguous_task"

    plan = turn_as(as_admin(), call(write, by_its_name(said(write))[write]))

    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", code)]
    assert json.loads(plan["append"][0]["content"])["error"]["code"] == code


@pytest.mark.parametrize("write", sorted(CHECKS))
def test_a_name_none_has_draws_no_card(write):
    datum, found, make = two(write)
    make(found)
    before = state()
    plan = turn_as(as_admin(), call(write, by_its_name("postres")[write]))
    assert (plan["confirm"], [row["code"] for row in plan["executed"]]) == (None, ["not_found"])
    assert state() == before


def test_every_write_of_tasks_that_takes_a_task_or_a_project_by_its_name_is_here():
    """No assistant write that takes a task or a project by its name escapes these cases: it checks it, or it is one of
    those that cannot (hub#1245)."""
    taking: dict[str, set[str]] = {}
    for op in task_writes():
        for datum in ("task", "project", "parent"):
            if datum in op.input.model_fields:
                taking.setdefault(op.name, set()).add(datum)
    expected = {write: {"task"} for write in ON_A_TASK} | {write: {"project"} for write in ON_A_PROJECT}
    for write, data in UNCHECKED.items():
        expected.setdefault(write, set()).update(data)
    assert taking == expected
    assert set(by_its_name("x")) == set(CHECKS)


def test_only_the_writes_that_take_their_record_by_its_name_check_it():
    """Ratchet: a check is a read before the card, which a write that takes no record by its name does not need (and
    whose refusal would hide its card): exactly these, each with the read of its own record."""
    declared = {op.name: assistant.check_of(op) for op in registry.values() if op.app_label == "task"}
    assert {name: read for name, read in declared.items() if read is not None} == CHECKS


def test_every_write_that_takes_a_task_or_a_project_by_its_name_reads_it_and_says_it_as_said_when_it_cannot():
    """With or without a check before it, a task or a project said by its name is read on its card, and stays on it as
    said when it cannot be read (two fit): never off it (``names(…, as_said=True)``, hub#1245)."""
    marks = {
        "task": names("task.task.detail", by="task", name=("title",), as_said=True),
        "project": names("task.project.detail", by="project", as_said=True),
        # The parent task is a task: the task's read takes it as its ``task``.
        "parent": names("task.task.detail", by="task", name=("title",), as_said=True),
    }
    reading = {
        (op.name, datum)
        for op in task_writes()
        for datum, mark in marks.items()
        if datum in op.input.model_fields and op.input.model_fields[datum].json_schema_extra == mark
    }
    assert reading == (
        {(write, "task") for write in ON_A_TASK}
        | {(write, "project") for write in ON_A_PROJECT}
        | {(write, datum) for write, data in UNCHECKED.items() for datum in data}
    )


def unchecked(write: str, datum: str, said_as: str) -> dict:
    """The data of a write of ``UNCHECKED`` with its ``datum`` said as ``said_as``."""
    if write == "task.comment.add":
        return {"task": said_as, "text": "Hecho"}
    if write == "task.task.create":
        return {"title": "Pedir hielo", datum: said_as}
    return {"id": str(Task.objects.get(title="Llamar al proveedor").id), "project": said_as}


UNCHECKED_CASES = sorted((write, datum) for write, data in UNCHECKED.items() for datum in data)


@pytest.mark.parametrize(("write", "datum"), UNCHECKED_CASES)
def test_a_name_two_fit_stays_on_the_card_of_a_write_that_cannot_check_it(write, datum):
    """A comment, a new task or a task moved to a project: «llamar» fits two tasks (or «apertura» two projects) and the
    card still says it as said."""
    make_task("Llamar al proveedor")
    make_task("Llamar al gestor")
    make_project("p-open", "Apertura del local")
    make_project("p-terrace", "Apertura de la terraza")
    word = "apertura" if datum == "project" else "llamar"
    assert fields_of(write, unchecked(write, datum, word))[datum]["value"] == word


# ── A task or a project said by its name with no read to check it with (hub#1245) ───────────────────────────────────
# Commenting on a task, creating a task in a project or under a parent task, or moving a task to a project, said by
# its name, has no read whose input fits to check it with: its card reads it by that name all the same, so what it
# found goes in its fingerprint and the yes holds to it.


@pytest.mark.parametrize(("write", "datum"), UNCHECKED_CASES)
def test_a_write_that_cannot_check_it_says_the_task_or_the_project_it_finds(write, datum):
    make_task("Llamar al proveedor")
    make_project("p-open", "Apertura del local")
    word, found = ("apertura", "Apertura del local") if datum == "project" else ("llamar", "Llamar al proveedor")
    assert fields_of(write, unchecked(write, datum, word))[datum]["value"] == found


@pytest.mark.parametrize(("write", "datum"), UNCHECKED_CASES)
def test_the_yes_to_a_write_that_cannot_check_it_touches_only_what_its_card_showed(write, datum):
    """«llamar» (or «apertura») shows the one that fits; somebody creates «Llamar» (or «Apertura») before the yes:
    nothing is commented, created or moved."""
    make_task("Llamar al proveedor")
    make_project("p-open", "Apertura del local")
    before = {}

    def meanwhile():
        if datum == "project":
            make_project("p-apertura", "Apertura")
        else:
            make_task("Llamar")
        before["state"] = state()

    word = "apertura" if datum == "project" else "llamar"
    done = yes_to_its_card(as_admin(), write, unchecked(write, datum, word), meanwhile=meanwhile)

    assert done["executed"] == []
    assert state() == before["state"]


# ── Not yet: a record that comes by its id with the name of another one beside it (hub#1250) ───────────────────────
# The write takes the task or the project by its id and never looks at the name; the card reads that name all the
# same and says both under one word («Tarea: Llamar al proveedor» and «Tarea: Pedir hielo»). The yes is still held to
# what the card read, and the write acts on the one of the id. Strict: once the card leaves out a name the write does
# not use, the first passes and its mark goes.

OTHER = {"task": ("Pedir hielo", "hielo"), "project": ("Reforma del baño", "reforma")}


def by_its_id_beside_another_name(write: str) -> dict:
    """The data of ``write`` with the id of the record that fits «llamar» or «apertura» and, beside it, a name only
    another one fits."""
    datum, found, make = two(write)
    record = make(found)
    other, word = OTHER[datum]
    make(other)
    return {**by_its_name(word)[write], "id": str(record.id)}


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="hub#1250: the card reads a name the write does not use")
@pytest.mark.parametrize("write", sorted(CHECKS))
def test_a_record_that_comes_by_its_id_names_no_other_one_said_beside_it(write):
    card = assistant.card(get(write), by_its_id_beside_another_name(write), "es", as_admin())
    assert OTHER[two(write)[0]][0] not in [field["value"] for field in card["fields"]]


@pytest.mark.parametrize("write", sorted(CHECKS))
def test_the_yes_to_a_record_that_comes_by_its_id_runs_on_it_whatever_name_is_said_beside_it(write):
    """Control of the above: the write acts on the record of the id, never on the one the name beside it fits."""
    arguments = by_its_id_beside_another_name(write)
    other = OTHER[two(write)[0]][0]

    def of_the_other() -> list:
        tasks, _, projects = state()
        return [row for row in tasks + projects if row[0] == other]

    before = of_the_other()
    done = yes_to_its_card(as_admin(), write, arguments)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert of_the_other() == before
