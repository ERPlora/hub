"""The assistant's card for a write of staff (FIX-HUB-STAFF-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Personal screens give it, never by the title pydantic makes up from
the field («Days», «Members»). The card is base's (``base.assistant.card``); the names are staff's: the titles of its
schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

SCREENS = json.loads((Path(apps.get_app_config("staff").path) / "frontend/locale/es.json").read_text())["staff"]

#: The data the Personal screens call by the code's very word, in Spanish too: the card says what the screen says.
SPELLED_ALIKE = {
    "color": SCREENS["members"]["form"]["color"],
    "bio": SCREENS["members"]["form"]["bio"],
}


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def staff_writes() -> list:
    return [op for op in registry.values() if op.app_label == "staff" and op.kind == "command" and assistant.is_tool(op)]


def test_no_datum_of_a_write_of_staff_reaches_a_spanish_card_by_its_technical_name():
    """Every write of staff the assistant may ask for, with all its data: each datum by a name of its own in Spanish
    (or the screen's word when Spanish spells it like the code), never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = staff_writes()
    assert len(writes) > 10  # positive control: the registry has staff's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            name, label = field["name"], field["label"]
            if name in SPELLED_ALIKE:
                assert label == SPELLED_ALIKE[name], (op.name, name)
            elif name not in screen and label == name.title().replace("_", " "):
                technical.setdefault(op.name, []).append(name)
    assert technical == {}


def test_the_card_names_a_schedules_week_as_its_form_does():
    week = [{"weekday": 0, "start_time": "09:00", "end_time": "17:00"}]
    for name in ("staff.schedule.create", "staff.schedule.update"):
        assert labels(assistant.card(get(name), {"days": week}, "es")) == [SCREENS["schedules"]["form"]["week"]]
        assert labels(assistant.card(get(name), {"days": week}, "en")) == ["Week"]


def test_the_card_names_the_people_of_a_batch_as_the_directory_does():
    batch = assistant.card(get("staff.member.bulk_create"), {"members": [{"first_name": "Ana", "last_name": "Gil"}]}, "es")
    assert labels(batch) == ["Miembros del personal"]
    english = assistant.card(get("staff.member.bulk_create"), {"members": [{"first_name": "Ana"}]}, "en")
    assert labels(english) == ["Staff members"]


def test_the_card_names_a_members_bio_and_colour_as_the_record_does():
    arguments = {"first_name": "Ana", "color": "#AABBCC", "bio": "Colorista."}
    record = SCREENS["members"]["form"]
    assert labels(assistant.card(get("staff.member.create"), arguments, "es")) == [
        record["firstName"],
        record["color"],
        record["bio"],
    ]


def test_the_card_paints_a_members_hourly_rate_as_money():
    """staff-business-currency: the hourly rate a write sends is an amount in the minor unit of the business's currency
    (the platform reads «in cents» so), and the card paints it as money in that currency with its decimals, never as
    the bare figure («1250» for 12,50 zł)."""
    for name in ("staff.member.create", "staff.member.update"):
        card = assistant.card(get(name), {"first_name": "Ana", "hourly_rate": 1250}, "es")
        rate = next(field for field in card["fields"] if field["name"] == "hourly_rate")
        assert (name, rate["kind"], rate["value"]) == (name, "money", 1250)
