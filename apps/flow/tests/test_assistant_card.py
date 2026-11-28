"""The assistant's card for an automation, a draft (``flow.draft.propose``) or a new one (``flow.flow.create``): its
name, when it starts and each step, in the words the Automations list and editor say them (FLOW-F17, BASE-F97).

«Quiero que cada vez que cierre la caja me quede apuntado repasar el cierre» drew «Proponer en Automatizaciones: Repasar
el cierre de caja · event · cash_register.session.closed · s1 · command · task.task.create · … · medium · 3 elementos»:
the owner could not tell what they were saying yes to (hub#2300). The expected words are read from the screens'
catalogues, as the editor reads them."""

import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get

from base import assistant

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB

LOCALE = Path(apps.get_app_config("flow").path) / "frontend" / "locale"
WORDS = {language: json.loads((LOCALE / f"{language}.json").read_text())["flow"] for language in ("en", "es")}

CLOSED = {"kind": "event", "event": "cash_register.session.closed"}
TASK = {
    "id": "s1",
    "kind": "command",
    "operation": "task.task.create",
    "params": {"title": "Repasar el cierre de caja", "priority": "medium"},
}
REVIEW = {"name": "Repasar el cierre de caja", "definition": {"trigger": CLOSED, "steps": [TASK]}, "notes": []}
#: What the owner must never read on the card: the event's, the action's, the step's and the list's codes.
CODES = ("cash_register.session.closed", "task.task.create", '"s1"', '"command"', '"event"', '"medium"')


def drawn(write: str, arguments: dict, language: str) -> list[dict]:
    return assistant.cards.card(get(write), arguments, language, ctx_for("hub_owner", language=language))["fields"]


def its_line(fields: list[dict]) -> list[tuple[str, object]]:
    """What a normal card's one line shows (``cardLine`` of @erplora/ui): its first three data that are not empty."""
    return [(field["name"], field["value"]) for field in fields if field["kind"] != "empty"][:3]


def when(language: str, key: str, **values) -> str:
    text = WORDS[language]["trigger"]["describe"][key]
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def event(language: str, name: str) -> str:
    return when(language, "event", event=WORDS[language]["events"][name.replace(".", "__")])


def action(language: str, name: str) -> str:
    return WORDS[language]["actions"][name.replace(".", "__")]


@pytest.mark.parametrize("language", ["es", "en"])
def test_the_card_of_a_draft_says_its_name_when_it_starts_and_its_steps(language):
    fields = drawn("flow.draft.propose", REVIEW, language)
    assert its_line(fields) == [
        ("name", "Repasar el cierre de caja"),
        ("when", event(language, "cash_register.session.closed")),
        ("steps", [action(language, "task.task.create")]),
    ]
    shown = json.dumps(fields, ensure_ascii=False)
    assert [code for code in CODES if code in shown] == []


@pytest.mark.parametrize(
    ("trigger", "key", "values", "clock"),
    [
        ({"kind": "schedule", "every": "day", "time": "10:00"}, "day", {}, {"es": "10:00", "en": "10:00 AM"}),
        ({"kind": "schedule", "every": "week", "weekday": 4, "time": "18:00"}, "week", {}, {"es": "18:00", "en": "6:00 PM"}),
        ({"kind": "schedule", "every": "month", "day": 1, "time": "09:30"}, "month", {"day": 1}, {"es": "9:30", "en": "9:30 AM"}),
    ],
)
def test_a_draft_on_a_schedule_says_it_as_the_list_does(trigger, key, values, clock):
    """The case of the birthdays: «Revisar cumpleaños de clientes cada mañana · schedule · day · 10:00 · crear_tarea…»,
    its time on the clock of the language, as the screens write it."""
    arguments = {**REVIEW, "definition": {"trigger": trigger, "steps": [TASK]}}
    for language in ("es", "en"):
        weekday = {"weekday": WORDS[language]["trigger"]["weekdays"][4]} if key == "week" else {}
        said = dict(its_line(drawn("flow.draft.propose", arguments, language)))["when"]
        assert re.sub(r"\s", " ", said) == when(language, key, **values, **weekday, time=clock[language])


def test_a_draft_with_no_trigger_starts_only_by_hand():
    arguments = {**REVIEW, "definition": {"steps": [TASK]}}
    assert dict(its_line(drawn("flow.draft.propose", arguments, "es")))["when"] == when("es", "manual")


def test_each_kind_of_step_a_draft_takes_is_said_as_the_editor_says_it():
    """A condition by its data and comparison, a wait by how long, an action by its words."""
    steps = [
        {"id": "big", "kind": "condition", "when": {"input.difference": {"neq": 0}}},
        {"id": "pause", "kind": "delay", "seconds": 3600},
        TASK,
    ]
    arguments = {**REVIEW, "definition": {"trigger": CLOSED, "steps": steps}}
    words = WORDS["es"]
    said = dict(its_line(drawn("flow.draft.propose", arguments, "es")))["steps"]
    assert said == [
        f"{words['fields']['difference']} {words['steps']['operators']['neq']} 0",
        words["steps"]["wait"].replace("{amount}", "1").replace("{unit}", words["steps"]["units"]["hours"]["one"]),
        action("es", "task.task.create"),
    ]


def test_the_card_of_a_new_automation_says_when_it_starts_and_its_steps():
    """The issue's comment: «Crear en Automatizaciones: Sumar puntos de fidelización al cobrar · event ·
    sale.sale.completed · 2 elementos»."""
    arguments = {
        "name": "Avisar de las ventas grandes",
        "trigger": {"kind": "event", "event": "sale.sale.completed"},
        "steps": [
            {"id": "big", "kind": "condition", "when": {"input.total": {"gte": 10000}}},
            {**TASK, "id": "task"},
        ],
    }
    for language in ("es", "en"):
        fields = drawn("flow.flow.create", arguments, language)
        words = WORDS[language]
        assert its_line(fields) == [
            ("name", "Avisar de las ventas grandes"),
            ("when", event(language, "sale.sale.completed")),
            (
                "steps",
                [f"{words['fields']['total']} {words['steps']['operators']['gte']} 10000", action(language, "task.task.create")],
            ),
        ]
        shown = json.dumps(fields, ensure_ascii=False)
        assert "sale.sale.completed" not in shown and "task.task.create" not in shown


def test_a_draft_that_runs_once_says_its_moment_at_the_businesss_hour():
    arguments = {**REVIEW, "definition": {"trigger": {"kind": "at", "at": "2026-12-01T09:00:00+00:00"}, "steps": [TASK]}}
    said = dict(its_line(drawn("flow.draft.propose", arguments, "es")))["when"]
    assert said.startswith(when("es", "at", date="")) and "1 dic 2026" in said and "09:00:00" not in said


#: What the card must never show, whatever the step: the id of a step, a name in snake case or the permission to call
#: another system («http:https://…»), as the screens' check of Automations reads it (``internal-codes.ts``).
INTERNAL = re.compile(r"(?<![\w.-])s\d+(?!\w)|(?<![\w.@/-])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![\w@])|http:https?://")


def said_on(fields: list[dict]) -> str:
    """What the owner reads on the card: each field's label and value."""
    def texts(value: object) -> list[str]:
        if isinstance(value, list):
            return [text for item in value for text in texts(item)]
        return [str(value)] if value not in (None, "") else []

    return " · ".join(text for field in fields for text in [*texts(field.get("label")), *texts(field.get("value"))])


@pytest.mark.parametrize("language", ["es", "en"])
def test_no_kind_of_step_shows_an_internal_code_on_the_card(language):
    """Every kind of step, with ids that would show if a step were named by its id (hub#2629): a draft takes the
    conditions, waits and actions, a new automation every kind."""
    steps = [
        {"id": "s1", "kind": "condition", "when": {"input.difference": {"neq": 0}}},
        {"id": "s2", "kind": "delay", "seconds": 3600},
        {**TASK, "id": "s3"},
        {"id": "s4", "kind": "query", "operation": "customer.customer.list", "params": {}, "result": "count"},
        {"id": "s5", "kind": "http", "method": "POST", "url": "https://api.example.com/x", "headers": {}, "body": "", "timeout": 10},
        {"id": "s6", "kind": "ask", "title": "¿Seguro?", "details": "", "role": "manager", "hours": 24, "on_no": "stop", "on_timeout": "no"},
        {"id": "s7", "kind": "assistant", "prompt": "Resume el día", "tools": [], "mode": "ask", "max_rounds": 6},
    ]
    proposed = {**REVIEW, "definition": {"trigger": CLOSED, "steps": steps[:3]}}
    created = {"name": "Repasar el cierre de caja", "trigger": CLOSED, "steps": steps}
    for write, arguments, said in (("flow.draft.propose", proposed, 3), ("flow.flow.create", created, 7)):
        fields = drawn(write, arguments, language)
        assert len(dict(its_line(fields))["steps"]) == said, write
        shown = said_on(fields)
        assert INTERNAL.findall(shown) == [], write
        assert [code for code in CODES if code.strip('"') in shown.split(" · ")] == [], write
    assert "api.example.com" in shown
