"""The platform's reaction to a customer's erasure: her personal links stop working and her device is forgotten."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.appointment.models.appointments import Appointment
from apps.online_booking.models import Booking

from .conftest import HUB_DB, booking_data, ctx_for, public, run

pytestmark = HUB_DB


def test_erasing_a_customer_revokes_her_links_and_forgets_her_device(salon):
    booked = public("book", booking_data(salon, "10:00"))
    other = public("book", booking_data(salon, "11:00", phone="699 000 111"))
    card = Appointment.objects.get(number=booked.number).customer
    system = ctx_for(permissions={"*"})
    assert (
        run("online_booking.customer.erase", {"id": str(card.id)}, ctx=system).changed
        == 1
    )
    booking = Booking.objects.get(appointment__number=booked.number)
    assert (booking.token_hash, booking.requester) == (None, "")
    with pytest.raises(NotFound):
        public("booking", {"token": booked.token})
    assert public("booking", {"token": other.token}).number == other.number
    assert (
        run("online_booking.customer.erase", {"id": str(card.id)}, ctx=system).changed
        == 0
    )


def test_only_the_platform_runs_the_reaction(salon):
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.customer.erase",
            {"id": str(salon.lucia.id)},
            role="hub_admin",
        )
