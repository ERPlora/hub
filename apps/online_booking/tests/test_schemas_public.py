"""The public page: a booking needs one to five different services, a time, a name and a mobile; the free times, the
services and a day; the customer's link, a long token."""

import uuid

import pytest
from pydantic import ValidationError

from apps.online_booking.schemas.public import PublicBookIn, PublicSlotsIn, TokenIn

from .schema_checks import fields_of


def test_the_public_booking_needs_a_service_a_time_a_name_and_a_mobile():
    with pytest.raises(ValidationError) as error:
        PublicBookIn()
    assert fields_of(error.value) == {"service_ids", "start", "name", "phone"}


def test_the_public_booking_takes_one_to_five_different_services_and_a_valid_email():
    service = str(uuid.uuid4())
    data = {"start": "2030-03-05T10:00", "name": "Marta", "phone": "612345678"}
    assert PublicBookIn(service_ids=[service], **data).email == ""
    with pytest.raises(ValidationError):
        PublicBookIn(service_ids=[], **data)
    with pytest.raises(ValidationError):
        PublicBookIn(service_ids=[str(uuid.uuid4()) for _ in range(6)], **data)
    with pytest.raises(ValidationError) as error:
        PublicBookIn(service_ids=[service, service], **data)
    assert fields_of(error.value) == {"service_ids"}
    with pytest.raises(ValidationError) as error:
        PublicBookIn(service_ids=[service], email="not an email", **data)
    assert fields_of(error.value) == {"email"}


def test_the_free_times_need_a_service_and_a_day():
    with pytest.raises(ValidationError) as error:
        PublicSlotsIn()
    assert fields_of(error.value) == {"service_ids", "date"}


def test_a_link_is_a_long_token():
    assert TokenIn(token="x" * 43).token == "x" * 43
    with pytest.raises(ValidationError):
        TokenIn(token="short")
