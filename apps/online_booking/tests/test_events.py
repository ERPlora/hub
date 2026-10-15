"""The online booking app's events and its reaction to Customers' erasure.

It announces a booking made on the page and a change of the page's settings; the rest of a booking's life is
announced by Citas. It reacts to ``customer.customer.erased`` (the customer's links stop working) through its
own operation, run as the system. The other events it hears change nothing here: the booking is the diary's.
"""

import pytest
from live.models import OutboxEvent

from apps.online_booking import events
from apps.online_booking.models import Booking

from .conftest import A, TUESDAY, booking_data, public

pytestmark = pytest.mark.django_db


def test_the_events_it_announces():
    assert events.ALL == [
        "online_booking.booking.created",
        "online_booking.settings.updated",
    ]


def test_it_reacts_only_to_an_erasure():
    assert events.REACTIONS == {
        "customer.customer.erased": "online_booking.customer.erase"
    }


def test_an_erased_card_revokes_the_links_as_the_system(salon):
    booked = public("book", booking_data(salon, "10:00"))
    card_id = Booking.objects.get().appointment.customer_id
    answer = events.react(
        A, "customer.customer.erased", {"id": str(card_id), "extra": "ignored"}
    )
    assert answer.changed == 1
    assert Booking.objects.get().token_hash is None
    assert booked.start.date() == TUESDAY


def test_an_event_it_does_not_hear_changes_nothing(salon):
    public("book", booking_data(salon, "10:00"))
    before = OutboxEvent.objects.count()
    assert (
        events.react(A, "customer.customer.merged", {"id": "x", "absorbed_id": "y"})
        is None
    )
    assert OutboxEvent.objects.count() == before
