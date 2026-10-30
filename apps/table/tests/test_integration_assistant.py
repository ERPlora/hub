"""The assistant's card for a write of table (FIX-HUB-TABLE-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is hub#258):
in Spanish, every datum it sends by the name the Tables screens give it, never by the title pydantic makes up from the
field («Color», «Into Table», «Line Ids»). The card is base's (``base.assistant.card``); the names are table's: the
titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
import re
import uuid
from pathlib import Path

import pytest
from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

from .conftest import (
    add_line,
    ctx_for,
    make_customer,
    make_hold,
    make_session,
    make_table,
    make_zone,
    open_check,
)

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


@pytest.mark.django_db
def test_the_card_names_the_table_a_check_goes_to_when_it_is_transferred(room):
    """«Transferir 4 a…»: the table it goes to (by id or by number) and that table's zone."""
    transfer = get("table.session.transfer")
    arguments = {"table": "4", "to_table_id": room["two"], "to_table": "7", "to_zone": "Terraza"}
    assert labels(assistant.card(transfer, arguments, "es", ctx=ctx_for(language="es"))) == [
        "Mesa",
        "Mesa de destino",
        "Mesa de destino",
        "Zona de destino",
    ]
    assert labels(assistant.card(transfer, arguments, "en", ctx=ctx_for())) == [
        "Table",
        "Destination table",
        "Destination table",
        "Destination zone",
    ]


@pytest.mark.django_db
def test_the_card_names_the_check_that_stays_when_two_tables_are_merged(room):
    """«Fusionar 4 con…»: the check that stays, as Sales' merge names it, or the table whose check stays."""
    merge = get("table.session.merge")
    arguments = {"into_session_id": room["other"], "into_table_id": room["two"], "into_table": "7", "into_zone": "Terraza"}
    assert labels(assistant.card(merge, arguments, "es", ctx=ctx_for(language="es"))) == [
        "Cuenta de destino",
        "Mesa de destino",
        "Mesa de destino",
        "Zona de destino",
    ]
    assert labels(assistant.card(merge, arguments, "en", ctx=ctx_for())) == [
        "Into check",
        "Destination table",
        "Destination table",
        "Destination zone",
    ]


@pytest.mark.django_db
def test_the_card_names_the_customer_and_the_reservation_of_a_table_seated(room):
    """Seating a table for a customer or a reservation: the table sheet's «Cliente» and «Reserva»."""
    seat = get("table.session.open")
    arguments = {"table": "4", "customer": "Ana", "reservation_id": room["booking"]}
    assert labels(assistant.card(seat, arguments, "es", ctx=ctx_for(language="es"))) == [
        "Mesa",
        SCREENS["sheet"]["customer"],
        SCREENS["sheet"]["reservation"],
    ]
    assert labels(assistant.card(seat, arguments, "en", ctx=ctx_for())) == [
        "Table",
        SCREENS_EN["sheet"]["customer"],
        SCREENS_EN["sheet"]["reservation"],
    ]


@pytest.mark.django_db
def test_the_card_names_the_lines_that_move_when_a_check_is_split(room):
    """«Dividir cuenta»: the lines that go to the new check, as Sales names the ones a split moves."""
    split = get("table.session.split")
    arguments = {"line_ids": [room["line"]]}
    assert labels(assistant.card(split, arguments, "es", ctx=ctx_for(language="es"))) == ["Líneas a mover"]
    assert labels(assistant.card(split, arguments, "en", ctx=ctx_for())) == ["Lines to move"]


@pytest.mark.django_db
def test_the_card_names_the_zone_a_table_moves_to_apart_from_the_zone_it_is_in(room):
    """Editing table 4 of the terrace to take it to the dining room: «Zona» is where it is, never where it goes."""
    update = get("table.table.update")
    arguments = {"table": "4", "zone": "Terraza", "move_to_zone": "Comedor"}
    assert labels(assistant.card(update, arguments, "es")) == ["Mesa", "Zona", "Mover a la zona"]
    assert labels(assistant.card(update, arguments, "en")) == ["Table", "Zone", "Move to zone"]
    moving = {"move_to_zone_id": room["room"]}
    assert labels(assistant.card(update, moving, "es", ctx=ctx_for(language="es"))) == ["Mover a la zona"]


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



# ── Which record a write touches, by the name the Tables screens give it (table-assistant-card) ─────

#: What a card never carries: an id.
AN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


@pytest.fixture
def room(product) -> dict[str, str]:
    """The ids a model sends of a room in service: table 5 of the terrace with its check of Sales (one line of Caña),
    table 2 of the dining room with its check and Pedro's reservation, table 7 without a zone with a closed check, a
    parked check, a bar check and a customer's card."""
    terrace, room = make_zone("Terraza"), make_zone("Comedor")
    five, two, seven = make_table("5", zone=terrace), make_table("2", zone=room), make_table("7")
    order, bar = open_check("Mesa 5"), open_check("Barra")
    booking = uuid.uuid7()
    make_hold(two, source="reservation", ref=str(booking), label="Pedro")
    records = {
        "terrace": terrace,
        "room": room,
        "five": five,
        "two": two,
        "seven": seven,
        "order": order,
        "bar": bar,
        "check": make_session(five, order_id=order.id),
        "other": make_session(two),
        "away": make_session(None, status="parked"),
        "closed": make_session(seven, status="closed"),
        "line": add_line(order.id, product(name="Caña", sku="CANA")).lines[-1],
        "customer": make_customer("Ana García"),
    }
    return {"booking": str(booking)} | {name: str(record.id) for name, record in records.items()}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "parked", "no_zone"), [("es", "Aparcada", "7 (sin zona)"), ("en", "Parked", "7 (no zone)")]
)
def test_every_record_a_write_of_table_names_by_its_id_is_named_on_its_card(room, language, parked, no_zone):
    """A table repeats its number across zones, so it is named with its zone («5 (Terraza)»), as the room's screens
    say it; a zone by its name; a check by where it is (its table, or parked); a check of Sales by its title, a
    customer by their card, a reservation by the name it paints on the table and a line by its name. Never by the
    id the model sent, in Spanish and in English."""
    writes = [
        ("table.zone.update", {"id": room["terrace"]}, {"id": "Terraza"}),
        ("table.zone.delete", {"id": room["room"]}, {"id": "Comedor"}),
        ("table.table.create", {"zone_id": room["terrace"]}, {"zone_id": "Terraza"}),
        ("table.table.bulk_create", {"zone_id": room["room"]}, {"zone_id": "Comedor"}),
        (
            "table.table.update",
            {"id": room["five"], "move_to_zone_id": room["room"]},
            {"id": "5 (Terraza)", "move_to_zone_id": "Comedor"},
        ),
        ("table.table.move", {"id": room["five"]}, {"id": "5 (Terraza)"}),
        ("table.table.delete", {"id": room["seven"]}, {"id": no_zone}),
        ("table.hold.place", {"table_id": room["five"]}, {"table_id": "5 (Terraza)"}),
        (
            "table.session.open",
            {
                "table_id": room["two"],
                "order_id": room["bar"],
                "customer_id": room["customer"],
                "reservation_id": room["booking"],
            },
            {"table_id": "2 (Comedor)", "order_id": "Barra", "customer_id": "Ana García", "reservation_id": "Pedro"},
        ),
        (
            "table.session.close",
            {"id": room["check"], "order_id": room["order"]},
            {"id": "5 (Terraza)", "order_id": "Mesa 5"},
        ),
        (
            "table.session.link_order",
            {"id": room["check"], "order_id": room["bar"]},
            {"id": "5 (Terraza)", "order_id": "Barra"},
        ),
        (
            "table.session.transfer",
            {"id": room["check"], "to_table_id": room["two"]},
            {"id": "5 (Terraza)", "to_table_id": "2 (Comedor)"},
        ),
        (
            "table.session.merge",
            {"id": room["check"], "into_session_id": room["other"], "into_table_id": room["two"]},
            {"id": "5 (Terraza)", "into_session_id": "2 (Comedor)", "into_table_id": "2 (Comedor)"},
        ),
        (
            "table.session.split",
            {"id": room["check"], "line_ids": [room["line"]]},
            {"id": "5 (Terraza)", "line_ids": ["Caña"]},
        ),
        ("table.session.set_guests", {"id": room["check"]}, {"id": "5 (Terraza)"}),
        ("table.session.park", {"id": room["check"]}, {"id": "5 (Terraza)"}),
        ("table.session.restore", {"id": room["away"], "table_id": room["seven"]}, {"id": parked, "table_id": no_zone}),
        ("table.session.delete", {"id": room["closed"]}, {"id": no_zone}),
    ]
    person = ctx_for(language=language)
    cards = {name: assistant.card(get(name), arguments, language, ctx=person) for name, arguments, _ in writes}
    assert {name: values(card) for name, card in cards.items()} == {name: expected for name, _, expected in writes}
    for name, card in cards.items():
        assert not AN_ID.search(json.dumps(card, ensure_ascii=False)), name


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "zone", "table", "check"), [("es", "Zona", "Mesa", "Cuenta"), ("en", "Zone", "Table", "Check")]
)
def test_the_record_a_write_acts_on_is_called_what_it_is_never_id(room, language, zone, table, check):
    """The datum ``id`` of a write is the zone, the table or the check it acts on: the card calls it so, never «Id»."""
    acting_on = {
        (zone, room["terrace"]): ("table.zone.update", "table.zone.delete"),
        (table, room["five"]): ("table.table.update", "table.table.move", "table.table.delete"),
        (check, room["check"]): (
            "table.session.close",
            "table.session.link_order",
            "table.session.transfer",
            "table.session.merge",
            "table.session.split",
            "table.session.set_guests",
            "table.session.park",
        ),
        (check, room["away"]): ("table.session.restore",),
        (check, room["closed"]): ("table.session.delete",),
    }
    person = ctx_for(language=language)
    called = {
        name: labels(assistant.card(get(name), {"id": record}, language, ctx=person))
        for (_, record), names in acting_on.items()
        for name in names
    }
    assert called == {name: [label] for (label, _), names in acting_on.items() for name in names}


@pytest.mark.django_db
def test_a_record_the_person_may_not_read_is_left_out_never_by_its_id(room):
    """The card reads each name as the person who confirms: a waiter without Sales' «view» sees no check of Sales, and
    nobody at hand (an automation's card) reads nothing for anybody."""
    seat = get("table.session.open")
    arguments = {"table_id": room["two"], "order_id": room["bar"]}
    tables_only = ctx_for(permissions={"table.view_table"})
    assert values(assistant.card(seat, arguments, "en", ctx=tables_only)) == {"table_id": "2 (Comedor)"}
    assert values(assistant.card(seat, arguments, "en")) == {}
