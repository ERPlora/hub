"""Appointments with the real Customers app: the card is Customers', made, merged and erased by its own
operations; the agenda names a customer by her name, phone or email, copies her contact, and reacts to
two cards merged and to an erased card.
"""

import pytest
from live.models import OutboxEvent

from apps.appointment import events
from apps.appointment.models import Appointment

from .conftest import A, MONDAY, make_member, make_service, make_tax, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


@pytest.fixture
def cast(db):
    make_service("Haircut", duration=30, tax=make_tax())
    make_member("Ana", "López")


def book(customer: str, start="10:00"):
    return run(
        "appointment.appointment.create",
        {"customer": customer, "services": [{"service": "Haircut"}], "staff": "Ana", "start": wall(MONDAY, start)},
    )


def relay(name: str):
    event = OutboxEvent.objects.filter(name=name).latest("id")
    return events.react(A, event.name, event.payload)


def test_a_card_made_in_customers_is_booked_by_its_phone_and_its_contact_copied(cast):
    card = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600 111 222", "email": "lucia@example.com"})
    out = book("600111222")
    assert (out.customer_id, out.customer_phone, out.customer_email) == (card.id, "+34600111222", "lucia@example.com")
    visits = run("appointment.appointment.list_for_customer", {"customer_id": str(card.id)})
    assert [row.number for row in visits.rows] == [out.number]


def test_merging_and_erasing_cards_in_customers_reach_the_agenda(cast):
    keep = run("customer.customer.create", {"name": "Lucía Pérez", "phone": "600111222"})
    twin = run("customer.customer.create", {"name": "Lucia P.", "phone": "600999888"})
    booked = book("600999888")
    run("customer.customer.merge", {"id": str(keep.id), "absorbed_id": str(twin.id)})
    assert relay("customer.customer.merged").changed == 1
    assert Appointment.objects.get(pk=booked.id).customer_id == keep.id
    run("customer.customer.erase", {"id": str(keep.id)})
    # The card and the one merged into it are the same person: one notice each, both relayed.
    erased = OutboxEvent.objects.filter(name="customer.customer.erased").order_by("id")
    assert sum(events.react(A, e.name, e.payload).changed for e in erased) == 1
    item = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (item.customer_name, item.customer_phone, item.number) == ("", "", booked.number)
