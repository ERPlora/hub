"""Reservations with the real Customers app: every reservation belongs to a card (found by its phone or
created), the guest's data are copies of it, and a merge or an erasure of the card reaches the bookings
when Customers announces them (RESERVATION-F06, F14, F21, F22). Nothing is mocked."""

import pytest
from live.context import system_context
from live.errors import InvalidPayload
from live.models import OutboxEvent

from apps.customer.models import Customer
from apps.reservation import events
from apps.reservation.models import Reservation, WaitlistEntry

from .conftest import A, book, ctx_for, make_customer, open_week, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture(autouse=True)
def week(db):
    open_week()


def test_a_guest_with_a_new_phone_gets_a_card_of_customers():
    out = book(
        guest_name="Ana García",
        guest_phone="600 111 222",
        guest_email="ana@x.es",
        ctx=ctx_for(EMPLOYEE),
    )
    card = Customer.objects.get(pk=out.customer_id)
    assert (card.name, card.phone, card.email, card.source) == (
        "Ana García",
        "+34600111222",
        "ana@x.es",
        "phone",
    )
    assert out.guest_phone == "+34600111222"


def test_a_guest_at_the_door_gets_a_walk_in_card():
    out = book(source="in_person")
    assert Customer.objects.get(pk=out.customer_id).source == "walk_in"


def test_the_card_with_that_phone_is_used_however_the_phone_is_typed():
    first = book(guest_phone="600111222")
    again = book(guest_phone="+34 600 11 12 22", date="2026-10-16")
    assert again.customer_id == first.customer_id
    assert Customer.objects.count() == 1


def test_among_cards_sharing_a_phone_the_one_with_the_guests_name_wins():
    make_customer("Marta López", phone="600111222")
    daughter = make_customer("Ana Garcia", phone="600111222")
    out = book(guest_name="ana garcía", guest_phone="600111222")
    assert out.customer_id == daughter.id


def test_a_chosen_card_gives_the_guests_name_phone_and_email():
    card = make_customer("Luis Pérez", phone="600333444", email="luis@x.es")
    out = book(customer_id=str(card.id), guest_name="", guest_phone="")
    assert (out.customer_id, out.guest_name, out.guest_phone, out.guest_email) == (
        card.id,
        "Luis Pérez",
        "+34600333444",
        "luis@x.es",
    )
    by_voice = book(
        customer="600 333 444", guest_name="", guest_phone="", date="2026-10-16"
    )
    assert by_voice.customer_id == card.id


def test_a_phone_customers_refuses_books_nothing_and_says_it_on_the_phone_field():
    with pytest.raises(InvalidPayload) as caught:
        book(guest_phone="12")
    assert set(caught.value.fields) == {"guest_phone"}
    assert Reservation.objects.count() == 0
    assert Customer.objects.count() == 0
    assert not OutboxEvent.objects.filter(name__startswith="reservation.").exists()


def test_a_waitlist_entry_is_linked_to_a_card_like_a_reservation():
    entry = run(
        "reservation.waitlist.create",
        {
            "guest_name": "Luis",
            "guest_phone": "600333444",
            "date": "2026-10-15",
            "preferred_time": "21:00",
            "party_size": 2,
        },
    )
    assert Customer.objects.get(pk=entry.customer_id).source == "walk_in"
    converted = run("reservation.waitlist.convert", {"id": str(entry.id)})
    assert converted.reservation.customer_id == entry.customer_id


def test_a_merge_in_customers_reaches_the_bookings_when_announced():
    survivor = make_customer("Ana García", phone="600111222")
    out = book(guest_name="Ana G.", guest_phone="600999888")
    absorbed = out.customer_id
    run(
        "customer.customer.merge",
        {"id": str(survivor.id), "absorbed_id": str(absorbed)},
        system_context(A),
    )
    merged = OutboxEvent.objects.get(name="customer.customer.merged")
    events.react(A, merged.name, merged.payload)
    assert Reservation.objects.get(pk=out.id).customer_id == survivor.id


def test_an_erasure_in_customers_reaches_the_bookings_when_announced():
    out = book(notes="Allergic to nuts")
    entry = run(
        "reservation.waitlist.create",
        {
            "customer_id": str(out.customer_id),
            "date": "2026-10-16",
            "preferred_time": "21:00",
            "party_size": 2,
        },
    )
    run(
        "customer.customer.erase",
        {"id": str(out.customer_id), "reason": "GDPR request"},
        system_context(A),
    )
    erased = OutboxEvent.objects.get(name="customer.customer.erased")
    events.react(A, erased.name, erased.payload)
    reservation = Reservation.objects.get(pk=out.id)
    assert (reservation.guest_name, reservation.guest_phone, reservation.notes) == (
        "",
        "",
        "",
    )
    assert WaitlistEntry.objects.get(pk=entry.id).guest_name == ""
    assert run("reservation.reservation.get", {"id": str(out.id)}).guest_name == ""


def test_seating_a_reservation_of_an_erased_card_seats_it_without_the_card():
    from .conftest import make_table

    table = make_table("5")
    out = book(table_id=str(table.id))
    run("customer.customer.erase", {"id": str(out.customer_id)}, system_context(A))
    seated = run("reservation.reservation.seat", {"id": str(out.id)})
    assert seated.status == "seated" and seated.table_session_id is not None


# ── Review of 2026-10-15 ─────────────────────────────────────────────────────────────────────────


def test_a_phone_typed_with_a_chosen_card_is_the_one_kept():
    # «The guest's name, phone and email are copies of the card unless others are typed» (WORKBOOK F06).
    card = make_customer("Luis Pérez", phone="600333444", email="luis@x.es")
    out = book(customer_id=str(card.id), guest_name="", guest_phone="611222333")
    assert (out.customer_id, out.guest_phone, out.guest_email) == (card.id, "611222333", "luis@x.es")
    entry = run(
        "reservation.waitlist.create",
        {"customer_id": str(card.id), "guest_phone": "622444555", "date": "2026-10-15", "preferred_time": "21:00", "party_size": 2},
    )
    assert (entry.customer_id, entry.guest_phone) == (card.id, "622444555")


def test_a_bad_phone_is_said_before_a_full_slot_is_offered_to_overbook():
    # Otherwise the host confirms «Book anyway?» and only then hears the phone is wrong.
    from .conftest import THURSDAY, make_reservation, make_slot

    Reservation.objects.all().delete()
    from apps.reservation.models import TimeSlot

    TimeSlot.objects.all().delete()
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    make_reservation()
    with pytest.raises(InvalidPayload) as caught:
        book(guest_phone="12")
    assert set(caught.value.fields) == {"guest_phone"}


def test_an_erased_guests_name_leaves_the_events_her_reservations_announced():
    # The contract with Tables puts the guest's name in status_changed and updated (the hold's label): erasing
    # the card empties it there too, as in the reservations themselves (RESERVATION-F22).
    from .conftest import set_rules

    set_rules(auto_confirm=True)
    hers = book(guest_name="Ana García", guest_phone="600111222")
    run("reservation.reservation.update", {"id": str(hers.id), "guest_name": "Ana G."})
    other = book(guest_name="Luis", guest_phone="600333444", date="2026-10-16")
    run("customer.customer.erase", {"id": str(hers.customer_id)}, system_context(A))
    erased = OutboxEvent.objects.get(name="customer.customer.erased")
    events.react(A, erased.name, erased.payload)
    names = {
        (row.payload["id"], row.name): row.payload.get("guest_name")
        for row in OutboxEvent.objects.filter(name__in=["reservation.reservation.status_changed", "reservation.reservation.updated"])
    }
    assert names == {
        (str(hers.id), "reservation.reservation.status_changed"): "",
        (str(hers.id), "reservation.reservation.updated"): "",
        (str(other.id), "reservation.reservation.status_changed"): "Luis",
    }


@pytest.mark.parametrize(("source", "card_source"), [("online", "website"), ("whatsapp", "whatsapp")])
def test_a_guest_who_books_herself_gets_a_card_from_where_she_booked(source, card_source):
    out = book(source=source, date="2026-10-16")
    assert Customer.objects.get(pk=out.customer_id).source == card_source
