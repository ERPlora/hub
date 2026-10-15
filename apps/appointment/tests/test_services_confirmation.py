"""A service marked «requires confirmation» in Services (``Service.requires_confirmation``) makes the customer's own
booking (online, WhatsApp) wait pending even with «confirm the customer's bookings automatically» on (APPOINTMENT-F18).
The front desk's bookings are never pending.
"""

import pytest

from .conftest import MONDAY, make_settings, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


def booking(salon, services, source: str, start: str = "10:00") -> dict:
    return {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(service.id)} for service in services],
        "staff_id": str(salon.ana.id),
        "start": wall(MONDAY, start),
        "source": source,
    }


def test_a_service_that_requires_confirmation_keeps_the_customers_booking_pending(salon):
    make_settings(auto_confirm_online=True)
    salon.colour.requires_confirmation = True
    salon.colour.save()
    assert run("appointment.appointment.create", booking(salon, [salon.cut], "online")).status == "confirmed"
    assert run("appointment.appointment.create", booking(salon, [salon.cut, salon.colour], "whatsapp", "12:00")).status == "pending"


def test_the_front_desk_is_never_pending(salon):
    salon.cut.requires_confirmation = True
    salon.cut.save()
    assert run("appointment.appointment.create", booking(salon, [salon.cut], "counter")).status == "confirmed"
