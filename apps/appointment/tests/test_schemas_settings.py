"""The settings stay in range."""

from apps.appointment.schemas.settings import SettingsIn

from .schema_checks import errors


def test_the_settings_stay_in_range():
    assert not errors(SettingsIn, min_booking_notice=0, max_advance_booking=0)
    assert "calendar_end_hour" in errors(SettingsIn, calendar_end_hour=25)
    assert "slot_interval" in errors(SettingsIn, slot_interval=0)
    assert "__all__" in errors(SettingsIn, calendar_start_hour=20, calendar_end_hour=8)
    assert "send_reminders" in errors(SettingsIn, send_reminders=True)
