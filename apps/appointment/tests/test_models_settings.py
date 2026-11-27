"""Models of the booking rules: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

from apps.appointment.models.settings import Settings

from .conftest import HUB_DB, refused

pytestmark = HUB_DB


def test_the_factory_settings_are_one_set():
    settings = Settings()
    assert (
        settings.default_duration,
        settings.min_booking_notice,
        settings.max_advance_booking,
        settings.allow_overlapping,
        settings.allow_customer_cancellation,
        settings.cancellation_notice_hours,
        settings.calendar_start_hour,
        settings.calendar_end_hour,
        settings.slot_interval,
        settings.auto_confirm_online,
    ) == (60, 60, 90, True, True, 24, 8, 20, 15, True)


def test_the_settings_are_a_single_row():
    Settings.objects.create()
    refused(lambda: Settings.objects.create())


def test_the_calendar_window_never_ends_before_it_starts():
    refused(
        lambda: Settings.objects.create(calendar_start_hour=20, calendar_end_hour=8)
    )
