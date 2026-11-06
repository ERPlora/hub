"""The assistant's confirmation card names each datum of a write of Tasks by a name of the app's own
(FIX-HUB-TASK-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title pydantic makes
up from the field («Assignee», «Member Id», «To Me»), nor by a word another app's catalog happens to lend. The card is
base's (``base.assistant.card``); the names are task's: the titles of its schemas and the ``verbose_name`` of its
models, with their Spanish in its catalog, as its screens (the task form, the task sheet and the projects) say them."""

import gettext
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen, technical_names

APP = Path(apps.get_app_config("task").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["task"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["task"]

#: The writes of Tasks the assistant calls, by name.
TOOLS = sorted(
    name for name, op in registry.items() if op.app_label == "task" and op.kind == "command" and assistant.is_tool(op)
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


@pytest.fixture
def named(monkeypatch):
    """Every record a write names by its id comes out named, as a person who may read it sees it: these tests are about
    what the card calls each datum, and a record nobody names is left out of it (hub#677)."""
    monkeypatch.setattr(assistant, "_reference", lambda value, prop, words: "Clean the store room")


def task_writes() -> list:
    return [get(name) for name in TOOLS]


def named_by_task(op, name: str, title: str | None) -> bool:
    """Whether task itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of
    one of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate
    is not a name of Tasks: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("task", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_task_reaches_a_spanish_card_by_its_technical_name(named):
    """Every write of task the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. But a project's colour, which the project form calls by the code's very word in
    Spanish too («Color»): the card says what the form says."""
    writes = task_writes()
    assert len(writes) >= 10  # positive control: the registry has task's writes
    assert technical_names(writes) == {"task.project.create": ["color"], "task.project.update": ["color"]}
    for name in ("task.project.create", "task.project.update"):
        assert labels(assistant.card(get(name), {"color": "#AA3300"}, "es")) == [SCREENS["projects"]["form"]["color"]]


def test_no_datum_of_a_write_of_task_borrows_its_name_from_another_apps_catalog(named):
    """``technical_names`` sees only a title nobody translates; one that another app's catalog happens to translate
    passes it and is still no name of Tasks: it changes if that app's text changes. So each datum is also named by
    task itself, by where the name comes from, not by the word (kept in hub#677)."""
    screen = named_by_the_screen()
    borrowed: dict[str, list[str]] = {}
    for op in task_writes():
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_task(op, datum, props[datum].get("title")):
                borrowed.setdefault(op.name, []).append(datum)
    assert borrowed == {}


@pytest.mark.parametrize(
    ("write", "list_"),
    [
        ("task.task.assign", "tasks"),
        ("task.task.complete", "tasks"),
        ("task.task.delete", "tasks"),
        ("task.task.set_status", "tasks"),
        ("task.task.update", "tasks"),
        ("task.project.delete", "projects"),
        ("task.project.update", "projects"),
    ],
)
def test_the_card_names_the_record_of_a_write_as_its_list_calls_one(named, write, list_):
    """The task or project a write acts on, titled with the word its list calls one of them, in each language
    («Tarea», «Project»): never «Id» (hub#677)."""
    op = get(write)
    for screens, language in ((SCREENS, "es"), (SCREENS_EN, "en")):
        one = screens[list_]["entity"]["one"]
        assert labels(assistant.card(op, {"id": "0192f0b2-3333-7000-8000-000000000003"}, language)) == [
            one[:1].upper() + one[1:]
        ], (write, language)


def test_the_card_names_the_task_of_a_comment_as_its_list_calls_one(named):
    """A comment says the task it goes on as the list of tasks calls one: «Tarea», «Task»."""
    add = get("task.comment.add")
    for screens, language in ((SCREENS, "es"), (SCREENS_EN, "en")):
        one = screens["tasks"]["entity"]["one"]
        assert labels(assistant.card(add, {"task_id": "0192f0b2-3333-7000-8000-000000000003"}, language)) == [
            one[:1].upper() + one[1:]
        ], language


def test_the_card_names_the_assignee_of_a_new_task_as_the_task_form(named):
    """By their name or by their id, the same person: «Assigned to», as the task form says it."""
    create = get("task.task.create")
    for arguments in ({"assignee": "Ana"}, {"assigned_to_id": "x"}):
        assert labels(assistant.card(create, arguments, "es")) == [SCREENS["form"]["assignee"]]
        assert labels(assistant.card(create, arguments, "en")) == [SCREENS_EN["form"]["assignee"]]


def test_the_card_names_whom_a_task_is_assigned_to_as_the_task_form(named):
    """Assigning an existing task names the person as creating one does: «Assigned to», by their name or by their id."""
    assign = get("task.task.assign")
    for arguments in ({"member": "Ana"}, {"member_id": "x"}):
        assert labels(assistant.card(assign, arguments, "es")) == [SCREENS["form"]["assignee"]]
        assert labels(assistant.card(assign, arguments, "en")) == [SCREENS_EN["form"]["assignee"]]


def test_the_card_names_assigning_to_oneself_as_the_task_sheet_button():
    assign = get("task.task.assign")
    assert labels(assistant.card(assign, {"to_me": True}, "es")) == [SCREENS["actions"]["assignToMe"]]
    assert labels(assistant.card(assign, {"to_me": True}, "en")) == [SCREENS_EN["actions"]["assignToMe"]]
