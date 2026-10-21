"""Online booking hears Customers through the worker's outbox relay, end to end (ONLINE_BOOKING-F09, F12): the
real Customers operations write their events, one tick of the worker's real loop hands them to Citas and to
this app (``base.relay``), and the inbox shows the booking on the kept card, or the erased customer's links stop
working — once, a second tick changing nothing.
"""

import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.errors import NotFound
from live.models import OutboxEvent

from apps.customer.models import Customer
from apps.online_booking.models import Booking
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import booking_data, public, run

pytestmark = pytest.mark.django_db

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


@pytest.fixture
def tick(monkeypatch):
    """One tick of the worker's real loop, without the SaaS (``register_apps``) and, inside the test's
    transaction, without releasing the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def once() -> None:
        stop = threading.Event()

        def wait(_seconds: float) -> bool:
            stop.set()
            return True

        now = timezone.now()
        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0

    return once


def delivered(name: str) -> dict[str, tuple[str, int]]:
    """``{app: (status, attempts)}`` of the deliveries of the newest ``name`` event."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    return {row.app_label: (row.status, row.attempts) for row in EventDelivery.objects.filter(event_id=event.id)}


def test_two_cards_merged_in_customers_leave_the_booking_on_the_kept_card(salon, tick):
    # ONLINE_BOOKING-F09: she booked on a duplicate card; Customers merges it into the one that stays.
    duplicate = Customer.objects.create(name="Lucia P.", phone="+34699999999")
    booked = public("book", booking_data(salon, "10:00", phone="699 999 999", name="Lucia P."))
    assert run("online_booking.booking.get", {"number": booked.number}).customer_id == duplicate.id
    run("customer.customer.merge", {"id": str(salon.lucia.id), "absorbed_id": str(duplicate.id)})

    tick()

    assert delivered("customer.customer.merged")["appointment"] == ("delivered", 1)
    row = run("online_booking.booking.get", {"number": booked.number})
    # On the kept card; the name saved on the booking does not change (Citas, APPOINTMENT-F23).
    assert (row.customer_id, row.customer_name) == (salon.lucia.id, "Lucia P.")
    # The link still works: it is the booking's, not the card's.
    assert public("booking", {"token": booked.token}).number == booked.number
    tick()
    assert delivered("customer.customer.merged")["appointment"] == ("delivered", 1)


def test_an_erased_customer_leaves_a_nameless_booking_and_no_working_link(salon, tick):
    # ONLINE_BOOKING-F12: Customers erases her data; Citas empties the appointment and this app revokes her link.
    booked = public("book", booking_data(salon, "10:00"))
    card = Customer.objects.get(phone="+34612345678")
    run("customer.customer.erase", {"id": str(card.id), "reason": "GDPR request"})
    assert public("booking", {"token": booked.token}).number == booked.number

    tick()

    deliveries = delivered("customer.customer.erased")
    assert (deliveries["appointment"], deliveries["online_booking"]) == (("delivered", 1), ("delivered", 1))
    row = run("online_booking.booking.get", {"number": booked.number})
    assert (row.customer_name, row.customer_phone, row.customer_email) == ("", "", "")
    booking = Booking.objects.get()
    assert (booking.token_hash, booking.requester) == (None, "")
    with pytest.raises(NotFound) as error:
        public("booking", {"token": booked.token})
    assert error.value.code == "online_booking.booking_not_found"
    tick()
    assert delivered("customer.customer.erased")["online_booking"] == ("delivered", 1)
