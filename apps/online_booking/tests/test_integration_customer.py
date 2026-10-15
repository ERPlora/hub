"""Online booking with the real Customers app (no doubles): the card found or created by the mobile, two
cards merged and a customer's data erased, each event delivered as the outbox relay will (phase 2) to the
reactions of Citas and of this app.
"""

import pytest
from live.models import OutboxEvent

from apps.appointment import events as appointment_events
from apps.customer.models import Customer
from apps.online_booking import events
from apps.online_booking.models import Booking

from .conftest import A, booking_data, public, run

pytestmark = pytest.mark.django_db


def deliver(name: str) -> None:
    """Hands every outbox event ``name`` to the reactions of Citas and of this app, as the relay does."""
    for event in OutboxEvent.objects.filter(name=name).order_by("id"):
        appointment_events.react(A, name, event.payload)
        events.react(A, name, event.payload)


def test_a_new_mobile_is_a_new_card_that_customers_finds_by_its_number(salon):
    public(
        "book", booking_data(salon, "10:00", phone="+34 699 000 111", name="Nora Vidal")
    )
    found = run("customer.customer.by_phone", {"phone": "699000111"})
    assert [card.name for card in found.rows] == ["Nora Vidal"]
    assert found.rows[0].phone == "+34699000111"


def test_a_known_mobile_books_on_the_card_customers_already_has(salon):
    public(
        "book", booking_data(salon, "10:00", phone="600 111 222", name="Lucía Pérez")
    )
    assert Customer.objects.filter(phone="+34600111222").count() == 1
    assert run("online_booking.booking.list").rows[0].customer_id == salon.lucia.id


def test_two_cards_merged_keep_the_booking_on_the_card_that_stays(salon):
    duplicate = Customer.objects.create(name="Lucia P.", phone="+34699999999")
    booked = public(
        "book", booking_data(salon, "10:00", phone="699 999 999", name="Lucia P.")
    )
    run(
        "customer.customer.merge",
        {"id": str(salon.lucia.id), "absorbed_id": str(duplicate.id)},
    )
    deliver("customer.customer.merged")
    row = run("online_booking.booking.get", {"number": booked.number})
    assert row.customer_id == salon.lucia.id
    # The link still works: it is the booking's, not the card's.
    assert public("booking", {"token": booked.token}).number == booked.number


def test_an_erased_customer_leaves_a_nameless_booking_and_no_working_link(salon):
    booked = public("book", booking_data(salon, "10:00"))
    card = Customer.objects.get(phone="+34612345678")
    run("customer.customer.erase", {"id": str(card.id), "reason": "GDPR request"})
    deliver("customer.customer.erased")
    row = run("online_booking.booking.get", {"number": booked.number})
    assert (row.customer_name, row.customer_phone, row.customer_email) == ("", "", "")
    booking = Booking.objects.get()
    assert (booking.token_hash, booking.requester) == (None, "")
    with pytest.raises(Exception) as error:
        public("booking", {"token": booked.token})
    assert getattr(error.value, "code", "") == "online_booking.booking_not_found"
