"""Cancelling by the link: the customer cancels her own booking, within the business's cancellation policy."""

import pytest
from live.errors import Conflict, NotFound

from apps.appointment.models import Appointment, History

from .conftest import HUB_DB, booking_data, make_rules, public

pytestmark = HUB_DB


def test_the_customer_cancels_with_her_link_within_the_policy(salon):
    booked = public("book", booking_data(salon, "10:00"))
    answer = public("cancel", {"token": booked.token, "reason": "Something came up"})
    assert (answer.status, answer.can_cancel) == ("cancelled", False)
    appointment = Appointment.objects.get(number=booked.number)
    assert (
        appointment.status,
        appointment.cancelled_by_customer,
        appointment.cancellation_reason,
    ) == (
        "cancelled",
        True,
        "Something came up",
    )
    assert (
        History.objects.get(appointment=appointment, action="cancelled").by_customer
        is True
    )


def test_the_link_keeps_the_cancellation_policy(salon):
    booked = public("book", booking_data(salon, "10:00"))
    make_rules(cancellation_notice_hours=48)
    with pytest.raises(Conflict) as error:
        public("cancel", {"token": booked.token})
    assert error.value.code == "appointment.cancellation_notice_required"
    make_rules(allow_customer_cancellation=False)
    with pytest.raises(Conflict) as error:
        public("cancel", {"token": booked.token})
    assert error.value.code == "appointment.customer_cancellation_disabled"
    assert Appointment.objects.get(number=booked.number).status == "confirmed"


def test_a_wrong_link_cancels_nothing(salon):
    with pytest.raises(NotFound) as error:
        public("cancel", {"token": "x" * 43})
    assert error.value.code == "online_booking.booking_not_found"
