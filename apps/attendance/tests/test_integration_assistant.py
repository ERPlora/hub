"""The assistant's card for a write of attendance (FIX-HUB-ATTENDANCE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Time tracking screens give it, never by the title pydantic
makes up from the field («Lat», «Lng», «Accuracy M»). The card is base's (``base.assistant.card``); the names are
attendance's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("attendance").path) / "frontend/locale"
SETTINGS = json.loads((FRONTEND / "es.json").read_text())["attendance"]["settings"]
SETTINGS_EN = json.loads((FRONTEND / "en.json").read_text())["attendance"]["settings"]
POSITION = {"lat": 40.4168, "lng": -3.7038, "accuracy_m": 12.0}


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def attendance_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "attendance" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_attendance_reaches_a_spanish_card_by_its_technical_name():
    """Every write of attendance the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = attendance_writes()
    # Positive control: the registry has attendance's writes, the ones that send a position among them.
    assert {"attendance.record.clock_in", "attendance.record.clock_out", "attendance.settings.update"} <= {
        op.name for op in writes
    }
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_position_of_a_clock_in_as_the_settings_screen_does():
    for name in ("attendance.record.clock_in", "attendance.record.clock_out"):
        op = get(name)
        assert labels(assistant.card(op, POSITION, "es")) == [
            SETTINGS["latitude"],
            SETTINGS["longitude"],
            "Precisión (m)",
        ], name
        assert labels(assistant.card(op, POSITION, "en")) == [
            SETTINGS_EN["latitude"],
            SETTINGS_EN["longitude"],
            "Accuracy (m)",
        ], name
