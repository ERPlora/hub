"""The schemas of the online booking app: what each operation takes (a 422 per field) and says to the assistant.

They are also the JSON Schema of the assistant's tools, so every input field carries a description.
"""

import uuid

import pytest
from pydantic import ValidationError

from apps.online_booking import schemas
from apps.online_booking.schemas import (
    BookingListIn,
    BookingRefIn,
    PublicBookIn,
    PublicSlotsIn,
    SettingsIn,
    TokenIn,
)


def fields_of(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}


def test_every_input_field_says_what_it_is():
    for name in dir(schemas):
        model = getattr(schemas, name)
        if (
            isinstance(model, type)
            and issubclass(model, schemas.In)
            and model is not schemas.In
        ):
            for field, info in model.model_fields.items():
                assert info.description, f"{name}.{field}"


def test_an_input_refuses_a_field_it_does_not_declare():
    with pytest.raises(ValidationError) as error:
        BookingListIn(colour="red")
    assert fields_of(error.value) == {"colour"}


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


def test_the_page_settings_check_the_colour_and_the_logo_address():
    assert SettingsIn(primary_color="#A1b2C3").primary_color == "#A1b2C3"
    assert SettingsIn(logo_url="").logo_url == ""
    assert (
        SettingsIn(logo_url="https://salon.example/logo.png").logo_url
        == "https://salon.example/logo.png"
    )
    with pytest.raises(ValidationError) as error:
        SettingsIn(primary_color="red", logo_url="javascript:alert(1)")
    assert fields_of(error.value) == {"primary_color", "logo_url"}


def test_the_limit_per_customer_is_one_to_fifty():
    assert SettingsIn(max_upcoming_per_customer=50).max_upcoming_per_customer == 50
    for wrong in (0, 51):
        with pytest.raises(ValidationError) as error:
            SettingsIn(max_upcoming_per_customer=wrong)
        assert fields_of(error.value) == {"max_upcoming_per_customer"}


def test_the_rules_keep_the_ranges_of_the_diary():
    with pytest.raises(ValidationError) as error:
        SettingsIn(
            min_booking_notice=-1,
            max_advance_booking=366,
            slot_interval=4,
            cancellation_notice_hours=721,
        )
    assert fields_of(error.value) == {
        "min_booking_notice",
        "max_advance_booking",
        "slot_interval",
        "cancellation_notice_hours",
    }


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
