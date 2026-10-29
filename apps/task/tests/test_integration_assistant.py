"""The assistant's confirmation card names each datum of a write of Tasks by a name of the app's own
(FIX-HUB-TASK-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258): in Spanish, never by the title pydantic makes
up from the field («Assignee», «Member Id», «To Me»), nor by a word another app's catalog happens to lend. The card is
base's (``base.assistant.card``); the names are task's: the titles of its schemas and the ``verbose_name`` of its
models, with their Spanish in its catalog, as its screens (the task form, the task sheet and the projects) say them."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("task").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["task"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["task"]

#: The writes of Tasks the assistant calls, by name.
TOOLS = sorted(
    name for name, op in registry.items() if op.app_label == "task" and op.kind == "command" and assistant.is_tool(op)
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


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


def test_no_datum_of_a_write_of_task_reaches_a_spanish_card_by_its_technical_name():
    """Every write of task the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 10  # positive control: the registry has task's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_task(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_the_assignee_of_a_new_task_as_the_task_form():
    """By their name or by their id, the same person: «Assigned to», as the task form says it."""
    create = get("task.task.create")
    for arguments in ({"assignee": "Ana"}, {"assigned_to_id": "x"}):
        assert labels(assistant.card(create, arguments, "es")) == [SCREENS["form"]["assignee"]]
        assert labels(assistant.card(create, arguments, "en")) == [SCREENS_EN["form"]["assignee"]]


def test_the_card_names_whom_a_task_is_assigned_to_as_the_task_form():
    """Assigning an existing task names the person as creating one does: «Assigned to», by their name or by their id."""
    assign = get("task.task.assign")
    for arguments in ({"member": "Ana"}, {"member_id": "x"}):
        assert labels(assistant.card(assign, arguments, "es")) == [SCREENS["form"]["assignee"]]
        assert labels(assistant.card(assign, arguments, "en")) == [SCREENS_EN["form"]["assignee"]]


def test_the_card_names_assigning_to_oneself_as_the_task_sheet_button():
    assign = get("task.task.assign")
    assert labels(assistant.card(assign, {"to_me": True}, "es")) == [SCREENS["actions"]["assignToMe"]]
    assert labels(assistant.card(assign, {"to_me": True}, "en")) == [SCREENS_EN["actions"]["assignToMe"]]
