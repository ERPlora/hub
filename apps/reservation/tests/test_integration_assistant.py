"""The assistant's card for a write of reservation (FIX-HUB-RESERVATION-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Reservations screens give it, never by the title pydantic
makes up from the field («Absorbed Id», «No Table», «Overbook»). The card is base's (``base.assistant.card``); the names
are reservation's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import json
from pathlib import Path

from django.apps import apps
from live.operations import get, registry

from base import assistant
from base.tests.test_assistant import named_by_the_screen

FRONTEND = Path(apps.get_app_config("reservation").path) / "frontend/locale"
SCREENS = json.loads((FRONTEND / "es.json").read_text())["reservation"]
SCREENS_EN = json.loads((FRONTEND / "en.json").read_text())["reservation"]

#: The writes that name a reservation by its guest and its day, and the ones that name a waitlist entry the same way.
RESERVATION_STEPS = ("cancel", "complete", "confirm", "delete", "no_show", "seat", "update")
WAITLIST_STEPS = ("convert", "delete", "update")


def labels(card: dict) -> list[str]:
    return [field["label"] for field in card["fields"]]


def reservation_writes() -> list:
    return [
        op
        for op in registry.values()
        if op.app_label == "reservation" and op.kind == "command" and assistant.is_tool(op)
    ]


def test_no_datum_of_a_write_of_reservation_reaches_a_spanish_card_by_its_technical_name():
    """Every write of reservation the assistant may ask for, with all its data: each datum by a name of its own in
    Spanish, never the one pydantic makes up."""
    screen = named_by_the_screen()
    writes = reservation_writes()
    assert len(writes) >= 15  # positive control: the registry has reservation's writes
    technical: dict[str, list[str]] = {}
    for op in writes:
        props = op.input.model_json_schema().get("properties", {})
        for field in assistant.card(op, dict.fromkeys(props, "x"), "es")["fields"]:
            if field["name"] not in screen and field["label"] == field["name"].title().replace("_", " "):
                technical.setdefault(op.name, []).append(field["name"])
    assert technical == {}


def test_the_card_names_the_duplicate_customer_whose_reservations_move():
    """Customers merges a duplicate card into the one that stays: the duplicate as its merge screen calls it."""
    reassign = get("reservation.customer.reassign")
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "es")) == ["Ficha duplicada"]
    assert labels(assistant.card(reassign, {"absorbed_id": "x"}, "en")) == ["Duplicate customer"]


def test_the_card_names_the_reservation_it_acts_on_by_its_guest_and_its_date():
    """«Confirmar la reserva de Ana del jueves»: the list's «Cliente» and the reservation's date, never a bare «Fecha»
    that an edit would repeat for the new one."""
    arguments = {"guest": "Ana", "day": "2026-10-29"}
    for step in RESERVATION_STEPS:
        op = get(f"reservation.reservation.{step}")
        assert labels(assistant.card(op, arguments, "es")) == [SCREENS["list"]["columns"]["guest"], "Fecha de la reserva"]
        assert labels(assistant.card(op, arguments, "en")) == [
            SCREENS_EN["list"]["columns"]["guest"],
            "Reservation date",
        ]
    edit = assistant.card(get("reservation.reservation.update"), {**arguments, "date": "2026-10-30"}, "es")
    assert labels(edit) == ["Cliente", "Fecha de la reserva", "Fecha"]


def test_the_card_names_the_waitlist_entry_it_acts_on_by_its_guest_and_its_date():
    """The waitlist's own columns, «Cliente» and «Fecha»."""
    arguments = {"guest": "Ana", "day": "2026-10-29"}
    columns, columns_en = SCREENS["waitlist"]["columns"], SCREENS_EN["waitlist"]["columns"]
    for step in WAITLIST_STEPS:
        op = get(f"reservation.waitlist.{step}")
        assert labels(assistant.card(op, arguments, "es")) == [columns["guest"], columns["date"]]
        assert labels(assistant.card(op, arguments, "en")) == [columns_en["guest"], columns_en["date"]]


def test_the_card_names_booking_a_full_slot_anyway_as_the_book_asks_it():
    """After «Esa franja ya está completa», the book asks «¿Reservar igualmente?» (a waitlist entry, «Convertir
    igualmente»): the card names the datum by that button."""
    for name in ("reservation.reservation.create", "reservation.reservation.update"):
        assert labels(assistant.card(get(name), {"overbook": True}, "es")) == [SCREENS["overbook"]["confirm"]]
        assert labels(assistant.card(get(name), {"overbook": True}, "en")) == [SCREENS_EN["overbook"]["confirm"]]
    convert = get("reservation.waitlist.convert")
    assert labels(assistant.card(convert, {"overbook": True}, "es")) == [SCREENS["overbook"]["convert"]]
    assert labels(assistant.card(convert, {"overbook": True}, "en")) == [SCREENS_EN["overbook"]["convert"]]


def test_the_card_names_the_zone_of_the_table_and_leaving_a_reservation_without_one():
    """Table 5 of the terrace, by its number and its zone; an edit that frees the table leaves it «Sin mesa»."""
    create = get("reservation.reservation.create")
    assert labels(assistant.card(create, {"table": "5", "zone": "Terraza"}, "es")) == ["Mesa", "Zona"]
    assert labels(assistant.card(create, {"table": "5", "zone": "Terraza"}, "en")) == ["Table", "Zone"]
    update = get("reservation.reservation.update")
    assert labels(assistant.card(update, {"zone": "Terraza", "no_table": True}, "es")) == ["Zona", "Sin mesa"]
    assert labels(assistant.card(update, {"zone": "Terraza", "no_table": True}, "en")) == ["Zone", "No table"]


def test_the_card_names_the_customer_a_channel_acts_for():
    """WhatsApp changing or cancelling the guest's own reservation: on behalf of her customer card."""
    for name in ("reservation.reservation.cancel", "reservation.reservation.update"):
        assert labels(assistant.card(get(name), {"on_behalf_of": "x"}, "es")) == ["En nombre del cliente"]
        assert labels(assistant.card(get(name), {"on_behalf_of": "x"}, "en")) == ["On behalf of the customer"]
