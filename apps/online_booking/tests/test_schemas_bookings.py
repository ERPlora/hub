"""The inbox of online bookings: a list pages by at most 100, and a booking is named by its id, its number or its
customer."""

import pytest
from pydantic import ValidationError

from apps.online_booking.schemas.bookings import BookingListIn, BookingRefIn

from .schema_checks import fields_of


def test_a_list_pages_by_at_most_100():
    assert BookingListIn().limit == 50
    assert BookingListIn().sort == "booked_at" and BookingListIn().dir == "desc"
    with pytest.raises(ValidationError):
        BookingListIn(limit=101)
    with pytest.raises(ValidationError) as error:
        BookingListIn(date_from="2030-03-05", date_to="2030-03-04")
    assert fields_of(error.value) == {"date_to"}


def test_a_booking_is_named_by_id_number_or_customer():
    assert BookingRefIn(number="APT-20300305-0001").number == "APT-20300305-0001"
    assert BookingRefIn(customer="Ana", date="2030-03-05").customer == "Ana"
    with pytest.raises(ValidationError) as error:
        BookingRefIn()
    assert "Say which booking" in str(error.value)
