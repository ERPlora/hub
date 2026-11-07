"""The public booking page reads a mobile written without prefix in the business's country, as Customers saves it
(hub#527, CUSTOMER-F11, CUSTOMER-F10): in a business of Poland, a visitor who books with «512 345 678» lands on the card
Customers saved as +48 512 345 678, never on a new Spanish one, and her bookings are found by those digits."""

import pytest

from apps.appointment.models import Appointment
from apps.customer.models import Customer
from base.models import Hub

from .conftest import at, booking_data, make_appointment, public, run, TUESDAY

pytestmark = pytest.mark.django_db

#: A Polish mobile written as a Pole types it: no prefix, in groups of three.
POLISH = "512 345 678"


@pytest.fixture
def in_poland(salon):
    """The business ``a`` registered in Poland, and Ola's card saved in Customers by the digits she gave."""
    Hub.objects.filter(slug="a").update(country="PL")
    salon.ola = run("customer.customer.create", {"name": "Ola Nowak", "phone": POLISH})
    return salon


def test_a_visitor_books_on_the_card_customers_saved_in_the_business_s_country(in_poland):
    cards = Customer.objects.count()
    booked = public("book", booking_data(in_poland, "10:00", phone=POLISH, name="Ola Nowak"))
    appointment = Appointment.objects.get(number=booked.number)
    assert (appointment.customer_id, appointment.customer_phone) == (in_poland.ola.id, "+48512345678")
    assert Customer.objects.count() == cards


def test_the_bookings_of_a_customer_are_found_by_her_digits_without_prefix(in_poland):
    card = Customer.objects.get(pk=in_poland.ola.id)
    made = make_appointment(card, in_poland.ana, [in_poland.cut], at(TUESDAY, "10:00"))
    listed = run("online_booking.booking.list", {"customer_name": POLISH})
    assert [row.id for row in listed.rows] == [made.id]
