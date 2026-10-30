"""The assistant's card for a write of reservation (FIX-HUB-RESERVATION-ASSISTANT-CARD-FIELDS-IN-ENGLISH; base's half is
hub#258): in Spanish, every datum it sends by the name the Reservations screens give it, never by the title pydantic
makes up from the field («Absorbed Id», «No Table», «Overbook»). The card is base's (``base.assistant.card``); the names
are reservation's: the titles of its schemas and the ``verbose_name`` of its models, with their Spanish in its catalog."""

import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from live.context import Scope
from live.operations import get, registry

from base import assistant
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant import named_by_the_screen
from base.tests.test_assistant_card_values import AN_ID

from .conftest import (
    TOMORROW,
    ctx_for,
    make_blocked,
    make_customer,
    make_entry,
    make_reservation,
    make_slot,
    make_table,
    make_zone,
)

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


@pytest.mark.django_db
def test_the_card_names_the_customer_a_channel_acts_for():
    """WhatsApp changing or cancelling the guest's own reservation: on behalf of her customer card, said by its name.
    (Since hub#416 a card leaves out a record it cannot name — a datum that is no id of any card, or an automation's
    card, which reads nothing —, so the card is asked as the person who confirms, about a card that exists.)"""
    ana = make_customer("Ana García")
    for name in ("reservation.reservation.cancel", "reservation.reservation.update"):
        for language, label in (("es", "En nombre del cliente"), ("en", "On behalf of the customer")):
            card = assistant.card(get(name), {"on_behalf_of": str(ana.id)}, language, ctx=ctx_for(language=language))
            assert said(card) == [(label, "Ana García")], (name, language)


# ── Each record a write names by its id, as its screen names it (FIX-HUB-RESERVATION-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS) ──
# Since hub#416 the card leaves out every id its schema does not mark with the read that names its record (before, the
# UUID showed). Reservation marks each one with a read by id of its own or of the app it requires (Customers, Tables),
# run as the person who confirms: a record they may not read, or of another business, is left out — never by its id.

#: Thursday 15 October 2026 at 21:00 as each language writes a day and a time on the card (base's CLDR words).
WHEN = {"es": "15 oct 2026 · 21:00", "en": "Oct 15, 2026 · 9:00 PM"}
#: The slot of Thursdays from 20:00 to 23:30, as the slots' list names it: its weekday and its hours.
DINNER = {"es": "Jueves · 20:00–23:30", "en": "Thursday · 8:00 PM–11:30 PM"}


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


def said(card: dict) -> list[tuple[str, object]]:
    return [(field["label"], field["value"]) for field in card["fields"]]


def by_an_id(card: dict) -> bool:
    return bool(AN_ID.search(json.dumps(card, ensure_ascii=False)))


def card_for(name: str, arguments: dict, language: str, ctx=None) -> dict:
    return assistant.card(get(name), arguments, language, ctx=ctx or ctx_for(language=language))


# RESERVATION-F06 «Tomar una reserva a mano», asked to the assistant: the card says for whom and at which table.
@pytest.mark.django_db
@pytest.mark.parametrize(("language", "customer", "table"), [("es", "Cliente", "Mesa"), ("en", "Customer", "Table")])
def test_booking_a_table_names_the_customer_and_the_table_never_by_their_ids(language, customer, table):
    ana = make_customer("Ana García")
    five = make_table("5", make_zone("Terraza"))
    arguments = {
        "customer_id": str(ana.id),
        "date": TOMORROW.isoformat(),
        "time": "21:00",
        "party_size": 4,
        "table_id": str(five.id),
    }
    card = card_for("reservation.reservation.create", arguments, language)
    named = [(label, value) for label, value in said(card) if label in (customer, table)]
    assert named == [(customer, "Ana García"), (table, "5")]
    assert not by_an_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_changing_a_reservation_names_it_its_new_table_and_the_customer_it_is_changed_for(language):
    ana = make_customer("Ana García")
    booked = make_reservation(customer_id=ana.id)
    seven = make_table("7")
    arguments = {"id": str(booked.id), "table_id": str(seven.id), "on_behalf_of": str(ana.id)}
    card = card_for("reservation.reservation.update", arguments, language)
    assert values(card) == {"id": f"Ana García · {WHEN[language]}", "table_id": "7", "on_behalf_of": "Ana García"}
    assert not by_an_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_step_of_a_reservation_names_it_by_its_guest_and_when_as_its_dialog_does(language):
    """«Confirm», «Seat», «Complete», «Cancel», «No-show», «Delete», «Edit»: the reservation as the book's own dialog
    says it before a step («Ana García · jueves, 15 de octubre · 21:00»), never by its id."""
    booked = make_reservation()
    for step in RESERVATION_STEPS:
        card = card_for(f"reservation.reservation.{step}", {"id": str(booked.id)}, language)
        assert values(card) == {"id": f"Ana García · {WHEN[language]}"}, step


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_step_of_a_waitlist_entry_names_it_by_its_guest_and_when_and_writing_one_down_its_customer(language):
    entry = make_entry()
    for step in WAITLIST_STEPS:
        card = card_for(f"reservation.waitlist.{step}", {"id": str(entry.id)}, language)
        assert values(card) == {"id": f"Luis Pérez · {WHEN[language]}"}, step
    ana = make_customer("Ana García")
    arguments = {"customer_id": str(ana.id), "date": TOMORROW.isoformat(), "preferred_time": "21:00", "party_size": 2}
    card = card_for("reservation.waitlist.create", arguments, language)
    assert values(card)["customer_id"] == "Ana García"
    assert not by_an_id(card)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "christmas", "afternoon"),
    [
        ("es", "25 dic 2026", "15 oct 2026 · 13:00–16:00"),
        ("en", "Dec 25, 2026", "Oct 15, 2026 · 1:00 PM–4:00 PM"),
    ],
)
def test_removing_a_slot_or_unblocking_a_date_names_it_as_its_list_does(language, christmas, afternoon):
    slot = make_slot()
    whole = make_blocked(dt.date(2026, 12, 25), reason="Navidad")
    some = make_blocked(TOMORROW, is_full_day=False, blocked_from=dt.time(13), blocked_until=dt.time(16))
    assert values(card_for("reservation.time_slot.delete", {"id": str(slot.id)}, language)) == {"id": DINNER[language]}
    unblock = "reservation.blocked_date.delete"
    assert values(card_for(unblock, {"id": str(whole.id)}, language)) == {"id": christmas}
    assert values(card_for(unblock, {"id": str(some.id)}, language)) == {"id": afternoon}


@pytest.mark.django_db
def test_a_record_the_person_may_not_read_is_left_out_never_by_its_id():
    """A host who books tables but may not read the customers' cards: the card names the table and leaves the customer
    out — as Customers would not show them that card."""
    ana = make_customer("Ana García")
    five = make_table("5")
    host = ctx_for(language="es", permissions={"reservation.add_reservation", "table.view_table"})
    arguments = {"customer_id": str(ana.id), "date": TOMORROW.isoformat(), "time": "21:00", "party_size": 2}
    card = card_for("reservation.reservation.create", {**arguments, "table_id": str(five.id)}, "es", ctx=host)
    assert "customer_id" not in values(card) and values(card)["table_id"] == "5"
    assert not by_an_id(card)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_of_another_business_is_left_out_never_by_its_id(hub_a, hub_b, monkeypatch):
    """Each business reads its own book: a reservation of business B named to business A's assistant is not there."""
    monkeypatch.setattr(context, "_test_fallback", None)
    with use_hub(hub_b):
        theirs = make_reservation()
    with use_hub(hub_a):
        mine = make_reservation(guest_name="Eva Gil")
        ours = ctx_for(scope=Scope("host", hub_a.slug), language="es")
        assert values(card_for("reservation.reservation.confirm", {"id": str(theirs.id)}, "es", ctx=ours)) == {}
        assert values(card_for("reservation.reservation.confirm", {"id": str(mine.id)}, "es", ctx=ours)) == {
            "id": f"Eva Gil · {WHEN['es']}"
        }
