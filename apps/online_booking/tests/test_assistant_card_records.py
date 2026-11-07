"""FIX-HUB-ONLINE_BOOKING-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#673): the card of a write of Online booking says
which booking, services and professional it acts on by their names, read as whoever asks, never by an id, and leaves
them out when that person may not read them or they are not there. A booking is an appointment of the diary, so it
goes as the diary says one — its customer, its day, its hour and its professional, as the inbox's «Cancel Lucía's
booking (…)?» dialog does —; a service and a professional of the page's booking by their names, as the page lists them.
"""

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import timezone
from live.context import OperationContext, Scope
from live.operations import get

from apps.online_booking.tests.conftest import (
    TUESDAY,
    A,
    at,
    ctx_for,
    make_appointment,
    make_customer,
    make_member,
    make_service,
    wall,
)
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"
WEDNESDAY = TUESDAY + dt.timedelta(days=1)

SCREENS = Path(apps.get_app_config("online_booking").path) / "frontend/locale"

#: The writes of the inbox, each on one booking named by its id.
ON_A_BOOKING = [
    "online_booking.booking.cancel",
    "online_booking.booking.complete",
    "online_booking.booking.confirm",
    "online_booking.booking.delete",
    "online_booking.booking.no_show",
]
#: The diary's two permissions to read an appointment: all of them, or one's own.
READS_THE_DIARY = {"appointment.view_appointment", "appointment.view_own_appointment"}

#: How the diary says Lucía's booking of Tuesday at 10:00 with Ana, and Pablo's of Wednesday at 17:30 with Bea.
LUCIAS = {
    "en": "Lucía Pérez · Tuesday, March 5, 2030 · 10:00 · Ana López",
    "es": "Lucía Pérez · martes, 5 de marzo de 2030 · 10:00 · Ana López",
}
PABLOS = {
    "en": "Pablo Ruiz · Wednesday, March 6, 2030 · 17:30 · Bea Ruiz",
    "es": "Pablo Ruiz · miércoles, 6 de marzo de 2030 · 17:30 · Bea Ruiz",
}


def screens(language: str) -> dict:
    return json.loads((SCREENS / f"{language}.json").read_text())["online_booking"]


def as_admin(language: str = "en", scope: Scope = A) -> OperationContext:
    return dataclasses.replace(ctx_for(scope=scope), language=language)


def without(permissions: set[str], language: str = "en") -> OperationContext:
    """An admin without ``permissions``: a combination no role has."""
    ctx = as_admin(language)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - permissions)


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or as_admin(language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


@dataclasses.dataclass
class Salon:
    """Two bookings of the page, each with every datum that could name it filled (customer, phone, email, note,
    professional, two services), and the services and professionals they were booked with."""

    lucias: object
    pablos: object
    cut: object
    colour: object
    ana: object
    bea: object


def make_salon() -> Salon:
    cut = make_service("Haircut", price=2000, duration=30)
    colour = make_service("Colour", price=4500, duration=60)
    ana = make_member("Ana", "López")
    bea = make_member("Bea", "Ruiz")
    lucia = make_customer("Lucía Pérez", phone="+34600111222", email="lucia@example.com")
    pablo = make_customer("Pablo Ruiz", phone="+34600333444", email="pablo@example.com")
    lucias = make_appointment(lucia, ana, [cut, colour], at(TUESDAY, "10:00"), number="APT-0001", notes="Corto")
    pablos = make_appointment(pablo, bea, [colour, cut], at(WEDNESDAY, "17:30"), number="APT-0002", notes="Rubio")
    return Salon(lucias, pablos, cut, colour, ana, bea)


# ── A booking, as the diary says it ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", ON_A_BOOKING)
def test_a_write_on_a_booking_says_it_as_the_diary_does(write, language):
    """The case the issue names, «online_booking.booking.cancel:id»: the booking by its customer, day, hour and
    professional, under the word the bookings list calls one («Reserva»)."""
    salon = make_salon()
    field = fields_of(write, {"id": str(salon.lucias.id)}, language).get("id", {})
    title = screens(language)["bookings"]["entity"]["one"].capitalize()
    assert (field.get("value"), field.get("label")) == (LUCIAS[language], title)


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own booking, never another of the list (the first, the last, the newest)."""
    salon = make_salon()
    bookings = (salon.lucias, salon.pablos)
    said = [shown("online_booking.booking.confirm", {"id": str(booking.id)}) for booking in bookings]
    assert said == [{"id": LUCIAS["en"]}, {"id": PABLOS["en"]}]


@pytest.mark.django_db
def test_a_cancellation_says_the_booking_beside_its_reason():
    salon = make_salon()
    said = shown("online_booking.booking.cancel", {"id": str(salon.pablos.id), "reason": "Llamó"}, "es")
    assert said == {"id": PABLOS["es"], "reason": "Llamó"}


# ── The page's booking: its services and its professional ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_pages_booking_says_its_services_and_its_professional_by_their_names(language):
    """Each service in the order sent, the professional chosen, under the words of the booking page."""
    salon = make_salon()
    sent = {
        "service_ids": [str(salon.colour.id), str(salon.cut.id)],
        "staff_id": str(salon.bea.id),
        "start": wall(TUESDAY, "12:00"),
        "name": "Marta Gil",
        "phone": "612 345 678",
    }
    fields = fields_of("online_booking.public.book", sent, language)
    page = screens(language)["preview"]
    said = [fields.get(datum, {}) for datum in ("service_ids", "staff_id")]
    assert [field.get("label") for field in said] == [page["services"], page["professional"]]
    assert [field.get("value") for field in said] == [["Colour", "Haircut"], "Bea Ruiz"]


@pytest.mark.django_db
def test_the_page_says_each_service_and_professional_sent_never_another():
    salon = make_salon()
    sent = {"service_ids": [str(salon.cut.id)], "staff_id": str(salon.ana.id), "start": wall(TUESDAY, "12:00")}
    said = shown("online_booking.public.book", {**sent, "name": "Marta Gil", "phone": "612 345 678"})
    assert (said.get("service_ids"), said.get("staff_id")) == (["Haircut"], "Ana López")


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("write", ON_A_BOOKING)
def test_what_the_person_may_not_read_in_the_diary_is_left_out_never_said_by_its_id(write):
    """Whoever may not read the diary is told no booking: a booking is an appointment of it."""
    salon = make_salon()
    arguments = {"id": str(salon.lucias.id)}
    assert shown(write, arguments) == {"id": LUCIAS["en"]}  # positive control
    said = shown(write, arguments, ctx=without(READS_THE_DIARY))
    assert said == {}
    assert no_id(said)


@pytest.mark.django_db
def test_services_and_a_professional_the_person_may_not_read_are_left_out():
    salon = make_salon()
    sent = {"service_ids": [str(salon.cut.id)], "staff_id": str(salon.ana.id), "start": wall(TUESDAY, "12:00")}
    assert shown("online_booking.public.book", sent).get("staff_id") == "Ana López"  # positive control
    said = shown("online_booking.public.book", sent, ctx=without({"service.view_service", "staff.view"}))
    assert (said.get("service_ids"), "staff_id" in said) == ([None], False)
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize("write", ON_A_BOOKING)
def test_a_booking_that_does_not_exist_is_left_out(write):
    said = shown(write, {"id": A_MISSING_ID})
    assert said == {}


@pytest.mark.django_db
def test_a_booking_deleted_meanwhile_is_left_out():
    salon = make_salon()
    arguments = {"id": str(salon.lucias.id)}
    assert shown("online_booking.booking.delete", arguments) == {"id": LUCIAS["en"]}  # positive control
    salon.lucias.deleted_at = timezone.now()
    salon.lucias.save(update_fields=["deleted_at"])
    assert shown("online_booking.booking.delete", arguments) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no booking, service nor professional: nothing is read."""
    salon = make_salon()
    op = get("online_booking.booking.cancel")
    card = assistant.card(op, {"id": str(salon.lucias.id), "reason": "Llamó"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"reason": "Llamó"}
    book = get("online_booking.public.book")
    card = assistant.card(book, {"service_ids": [str(salon.cut.id)], "staff_id": str(salon.ana.id)}, "en")
    assert no_id(card) and "staff_id" not in {field["name"] for field in card["fields"]}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_booking_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = as_admin(scope=Scope("host", hub_a.slug)), as_admin(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        salon = make_salon()
        arguments = {"id": str(salon.lucias.id)}
        assert shown("online_booking.booking.confirm", arguments, ctx=in_a) == {"id": LUCIAS["en"]}  # positive control
    with use_hub(hub_b):
        assert shown("online_booking.booking.confirm", arguments, ctx=in_b) == {}
