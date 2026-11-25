"""The book's rules: a change sends only what changes, within its bounds, and the days ahead bind only the guest
who books herself."""

from apps.reservation.schemas.settings import SettingsIn, SettingsOut

from .conftest import errors


def test_the_settings_change_only_what_is_sent_within_their_bounds():
    assert SettingsIn.model_validate({"auto_confirm": True}).model_fields_set == {
        "auto_confirm"
    }
    assert "max_party_size" in errors(SettingsIn, {"max_party_size": 0})
    assert "default_duration_minutes" in errors(
        SettingsIn, {"default_duration_minutes": 24 * 60 + 1}
    )


def test_the_days_ahead_say_they_bind_only_the_guest_who_books_herself():
    for schema in (SettingsIn, SettingsOut):
        description = schema.model_fields["max_advance_days"].description
        assert "online" in description and "WhatsApp" in description, schema
