"""The assistant's card for a write of table (FIX-HUB-TABLE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Tables screens give it, never by the title pydantic makes up from the
field («Color», «Into Table», «Line Ids»). The card is base's (``base.assistant.card``); the names are table's: the
titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("table").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["table"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["table"]


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def table_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "table" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_table_reaches_a_spanish_card_by_its_technical_name():
    """Every write of table the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = table_writes()
    assert len(writes) > 20  # positive control: the registry has table's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_colour_of_a_zone_never_by_its_technical_name():
    """The zone form's «Color», said with whose colour it is: «Color» alone is the field's own name."""
    assert SCREENS["zoneForm"]["color"] == "Color"
    for name in ("table.zone.create", "table.zone.update"):
        assert labels(assistant.card(get(name), {"color": "success"}, "es")) == ["Color de la zona"]
        assert labels(assistant.card(get(name), {"color": "success"}, "en")) == ["Zone colour"]


def test_the_card_names_the_table_a_check_goes_to_when_it_is_transferred():
    """«Transferir 4 a…»: the table it goes to (by id or by number) and that table's zone."""
    transfer = get("table.session.transfer")
    arguments = {"table": "4", "to_table_id": "x", "to_table": "7", "to_zone": "Terraza"}
    assert labels(assistant.card(transfer, arguments, "es")) == [
        "Mesa",
        "Mesa de destino",
        "Mesa de destino",
        "Zona de destino",
    ]
    assert labels(assistant.card(transfer, arguments, "en")) == [
        "Table",
        "Destination table",
        "Destination table",
        "Destination zone",
    ]


def test_the_card_names_the_check_that_stays_when_two_tables_are_merged():
    """«Fusionar 4 con…»: the check that stays, as Sales' merge names it, or the table whose check stays."""
    merge = get("table.session.merge")
    arguments = {"into_session_id": "x", "into_table_id": "y", "into_table": "7", "into_zone": "Terraza"}
    assert labels(assistant.card(merge, arguments, "es")) == [
        "Cuenta de destino",
        "Mesa de destino",
        "Mesa de destino",
        "Zona de destino",
    ]
    assert labels(assistant.card(merge, arguments, "en")) == [
        "Into check",
        "Destination table",
        "Destination table",
        "Destination zone",
    ]


def test_the_card_names_the_customer_and_the_reservation_of_a_table_seated():
    """Seating a table for a customer or a reservation: the table sheet's «Cliente» and «Reserva»."""
    seat = get("table.session.open")
    arguments = {"table": "4", "customer": "Ana", "reservation_id": "x"}
    assert labels(assistant.card(seat, arguments, "es")) == [
        "Mesa",
        SCREENS["sheet"]["customer"],
        SCREENS["sheet"]["reservation"],
    ]
    assert labels(assistant.card(seat, arguments, "en")) == [
        "Table",
        SCREENS_EN["sheet"]["customer"],
        SCREENS_EN["sheet"]["reservation"],
    ]


def test_the_card_names_the_lines_that_move_when_a_check_is_split():
    """«Dividir cuenta»: the lines that go to the new check, as Sales names the ones a split moves."""
    split = get("table.session.split")
    assert labels(assistant.card(split, {"line_ids": ["x"]}, "es")) == ["Líneas a mover"]
    assert labels(assistant.card(split, {"line_ids": ["x"]}, "en")) == ["Lines to move"]


def test_the_card_names_the_zone_a_table_moves_to_apart_from_the_zone_it_is_in():
    """Editing table 4 of the terrace to take it to the dining room: «Zona» is where it is, never where it goes."""
    update = get("table.table.update")
    arguments = {"table": "4", "zone": "Terraza", "move_to_zone": "Comedor"}
    assert labels(assistant.card(update, arguments, "es")) == ["Mesa", "Zona", "Mover a la zona"]
    assert labels(assistant.card(update, arguments, "en")) == ["Table", "Zone", "Move to zone"]
    assert labels(assistant.card(update, {"move_to_zone_id": "x"}, "es")) == ["Mover a la zona"]


def test_the_card_names_the_numbering_of_tables_created_at_once():
    bulk = get("table.table.bulk_create")
    arguments = {"prefix": "T", "start_number": 10}
    assert labels(assistant.card(bulk, arguments, "es")) == ["Prefijo del número", "Primer número"]
    assert labels(assistant.card(bulk, arguments, "en")) == ["Number prefix", "First number"]


def test_the_card_names_the_guest_of_a_reservation_that_holds_a_table():
    """A reservation of Reservations that holds or moves its table: the name on it, as Reservations calls it."""
    for name in ("table.hold.sync_reservation", "table.hold.move_reservation"):
        assert labels(assistant.card(get(name), {"guest_name": "Ana"}, "es")) == ["Nombre del cliente"]
        assert labels(assistant.card(get(name), {"guest_name": "Ana"}, "en")) == ["Guest's name"]
