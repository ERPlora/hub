"""The assistant's card names every datum a write of Automations sends (FIX-HUB-FLOW-ASSISTANT-CARD-FIELDS-IN-ENGLISH;
base's half is hub#258): in Spanish, by the name the Automations screens give it, never by the title pydantic makes up
from the field («Actor», «Draft Id», «Event Id»). The card is base's (``base.assistant.card``); the names are flow's: the
titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog. Where the editor
already has words for the datum (``flow.fields.<name>``, ``frontend/locale/{en,es}.json``), the card says the same."""

import gettext
import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

APP = Path(apps.get_app_config("flow").path)
SCREENS = json.loads((APP / "frontend/locale/es.json").read_text())["flow"]
SCREENS_EN = json.loads((APP / "frontend/locale/en.json").read_text())["flow"]

#: The writes of Automations the assistant calls, by name.
TOOLS = sorted(
    name for name, op in registry.items() if op.app_label == "flow" and op.kind == "command" and assistant.is_tool(op)
)


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def named_by_flow(op, name: str, title: str | None) -> bool:
    """Whether flow itself names the datum ``name`` of ``op``: by its schema's own title, by the ``verbose_name`` of one
    of its models, or by its own catalog. A title pydantic made up that another app's catalog happens to translate is
    not a name of Automations: it changes if that app's text changes."""
    made_up = assistant._generated_title(name)
    with (APP / "locale/es/LC_MESSAGES/django.mo").open("rb") as compiled:
        own = gettext.GNUTranslations(compiled)
    return (
        bool(title and title != made_up)
        or assistant._verbose_name("flow", op.name.split(".")[1], name) is not None
        or own.gettext(made_up) != made_up
    )


def test_no_datum_of_a_write_of_flow_reaches_a_spanish_card_by_its_technical_name():
    """Every write of flow the assistant may ask for, with all its data: each datum by a name of its own in Spanish,
    never the one pydantic makes up. By where the name comes from, not by the word."""
    screen = named_by_the_screen()
    assert len(TOOLS) >= 20  # positive control: the registry has flow's writes
    technical: dict[str, list[str]] = {}
    for name in TOOLS:
        op = get(name)
        props = assistant._schema(op).get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            datum = field["name"]
            if datum not in screen and not named_by_flow(op, datum, props[datum].get("title")):
                technical.setdefault(name, []).append(datum)
    assert technical == {}


def test_the_card_names_who_caused_an_event_as_the_editor():
    """An event an automation reacts to: who caused it is «Quién lo hizo», as the editor's «Which data?» says it."""
    react = get("flow.run.react")
    assert labels(assistant.card(react, {"actor": "x"}, "es")) == [SCREENS["fields"]["actor"]] == ["Quién lo hizo"]
    assert labels(assistant.card(react, {"actor": "x"}, "en")) == [SCREENS_EN["fields"]["actor"]]


def test_the_card_names_the_event_an_automation_reacts_to():
    arguments = {"event_id": "x", "event": "sale.sale.completed", "payload": {"total": 1}}
    react = get("flow.run.react")
    assert labels(assistant.card(react, arguments, "es")) == [
        "Referencia de lo que pasó",
        "Qué pasó",
        SCREENS["picker"]["input"],
    ]
    assert labels(assistant.card(react, arguments, "en")) == [
        "Reference of what happened",
        "What happened",
        SCREENS_EN["picker"]["input"],
    ]


def test_the_card_names_how_it_starts_and_the_draft_as_the_list():
    for name in ("flow.flow.create", "flow.flow.update"):
        arguments = {"trigger": {"kind": "manual"}}
        assert labels(assistant.card(get(name), arguments, "es")) == [SCREENS["list"]["filterTrigger"]]
        assert labels(assistant.card(get(name), arguments, "en")) == [SCREENS_EN["list"]["filterTrigger"]]
    create = get("flow.flow.create")
    assert labels(assistant.card(create, {"draft_id": "x"}, "es")) == [SCREENS["drafts"]["badge"]]
    assert labels(assistant.card(create, {"draft_id": "x"}, "en")) == [SCREENS_EN["drafts"]["badge"]]


def test_the_card_names_what_an_automation_may_do_as_its_permissions_tab():
    grant = get("flow.flow.grant")
    arguments = {"operations": ["sale.sale.void"]}
    assert labels(assistant.card(grant, arguments, "es")) == [SCREENS["editor"]["tabs"]["permissions"]]
    assert labels(assistant.card(grant, arguments, "en")) == [SCREENS_EN["editor"]["tabs"]["permissions"]]


def test_the_card_names_the_answer_to_a_question():
    """«Waiting for your answer» asks yes or no: the card says the person's answer, «Respuesta: Sí»."""
    answer = get("flow.question.answer")
    assert labels(assistant.card(answer, {"approve": True}, "es")) == ["Respuesta"]
    assert labels(assistant.card(answer, {"approve": True}, "en")) == ["Answer"]


def test_the_card_names_a_secrets_value_as_the_secrets_screen():
    secret = get("flow.secret.set")
    assert labels(assistant.card(secret, {"value": "x"}, "es")) == [SCREENS["secrets"]["value"]]
    assert labels(assistant.card(secret, {"value": "x"}, "en")) == [SCREENS_EN["secrets"]["value"]]


def test_the_card_names_how_a_call_ended_with_the_words_of_its_step():
    """A call of a run leaves ``status``, ``body`` and ``truncated`` to the next steps: the card names them as the
    editor does, and what went wrong as the history's technical text."""
    record = get("flow.run.record_call")
    arguments = {"kind": "ok", "body": "x", "truncated": False, "detail": "x"}
    assert labels(assistant.card(record, arguments, "es")) == [
        "Cómo terminó",
        SCREENS["fields"]["body"],
        SCREENS["fields"]["truncated"],
        "Texto técnico",
    ]
    assert labels(assistant.card(record, arguments, "en")) == [
        "How it ended",
        SCREENS_EN["fields"]["body"],
        SCREENS_EN["fields"]["truncated"],
        "Technical text",
    ]
