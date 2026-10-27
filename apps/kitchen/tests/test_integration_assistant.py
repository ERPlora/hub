"""The assistant's card for a write of kitchen (FIX-HUB-KITCHEN-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Kitchen screens give it, never by the title pydantic makes
up from the field («Channel», «Item Ids», «From Order Id»). The card is base's (``base.assistant.card``); the names are
kitchen's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("kitchen").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["kitchen"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["kitchen"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def kitchen_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "kitchen" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_kitchen_reaches_a_spanish_card_by_its_technical_name():
    """Every write of kitchen the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = kitchen_writes()
    assert len(writes) > 15  # positive control: the registry has kitchen's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_type_and_the_dishes_of_a_round_sent_to_the_kitchen():
    """Sending a check and the round Sales fires: the dine-in, takeaway or delivery of the ticket and its dishes."""
    dishes, dishes_en = SCREENS["form"]["dishes"], SCREENS_EN["form"]["dishes"]
    receive = get("kitchen.ticket.receive")
    arguments = {"channel": "takeaway", "items": [{"order_item_id": "x"}]}
    assert labels(assistant.card(receive, arguments, "es")) == ["Tipo de comanda", dishes]
    assert labels(assistant.card(receive, arguments, "en")) == ["Ticket type", dishes_en]
    send = get("kitchen.ticket.send")
    assert labels(assistant.card(send, {"channel": "delivery"}, "es")) == ["Tipo de comanda"]
    assert labels(assistant.card(send, {"channel": "delivery"}, "en")) == ["Ticket type"]


def test_the_card_names_the_dishes_of_a_ticket_made_by_hand_and_the_ones_marked_ready():
    dishes, dishes_en = SCREENS["form"]["dishes"], SCREENS_EN["form"]["dishes"]
    create = get("kitchen.ticket.create")
    assert labels(assistant.card(create, {"items": [{"name": "Tortilla"}]}, "es")) == [dishes]
    assert labels(assistant.card(create, {"items": [{"name": "Tortilla"}]}, "en")) == [dishes_en]
    for name in ("kitchen.item.bump", "kitchen.item.recall"):
        assert labels(assistant.card(get(name), {"item_ids": ["x"]}, "es")) == [dishes]
        assert labels(assistant.card(get(name), {"item_ids": ["x"]}, "en")) == [dishes_en]


def test_the_card_names_the_checks_of_a_merge_as_sales_does():
    """Two checks Sales merged: the one absorbed and the one that stays, by the names Sales' merge gives them."""
    sync = get("kitchen.ticket.sync")
    arguments = {"from_order_id": "x", "to_order_id": "y"}
    assert labels(assistant.card(sync, arguments, "es")) == ["Cuenta de origen", "Cuenta de destino"]
    assert labels(assistant.card(sync, arguments, "en")) == ["From check", "Into check"]


def test_the_card_names_the_colour_of_a_station_never_by_its_technical_name():
    """«Color» is written as the field is: the station's form names it, and the card says whose colour it is."""
    for name in ("kitchen.station.create", "kitchen.station.update"):
        assert labels(assistant.card(get(name), {"color": "#F97316"}, "es")) == ["Color de la estación"]
        assert labels(assistant.card(get(name), {"color": "#F97316"}, "en")) == ["Station colour"]
