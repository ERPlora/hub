"""The settings of the public page: its colour and logo, the limit per customer and the diary's rules, each in range."""

import pytest
from pydantic import ValidationError

from apps.online_booking.schemas.settings import SettingsIn

from .schema_checks import fields_of


def test_the_page_settings_check_the_colour_and_name_the_logo_an_upload_answered():
    assert SettingsIn(primary_color="#A1b2C3").primary_color == "#A1b2C3"
    assert SettingsIn(logo="").logo == ""
    assert SettingsIn(logo="0123456789abcdef.webp").logo == "0123456789abcdef.webp"
    with pytest.raises(ValidationError) as error:
        SettingsIn(primary_color="red", logo="https://salon.example/logo.png")
    assert fields_of(error.value) == {"primary_color", "logo"}
    with pytest.raises(ValidationError) as error:
        SettingsIn(logo_url="https://salon.example/logo.png")
    assert fields_of(error.value) == {"logo_url"}


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
