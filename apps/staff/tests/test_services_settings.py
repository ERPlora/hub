"""The working day a new schedule starts from. A refused command leaves no trace: no row, no event."""

import datetime as dt

import pytest
from live.errors import InvalidPayload, PermissionDenied
from live.models import OutboxEvent

from apps.staff import events
from apps.staff.models import StaffSettings
from apps.staff.schemas.settings import SettingsIn
from apps.staff.services.settings import update_settings

from .conftest import HUB_DB, A, ctx_for, outbox, run

pytestmark = HUB_DB


# staff.settings.update (STAFF-F22)


def test_the_first_save_creates_the_settings_with_the_defaults_for_the_rest():
    settings = run("staff.settings.update", SettingsIn(default_break_duration=30))
    assert settings.model_dump() == {
        "default_work_start": "09:00",
        "default_work_end": "18:00",
        "default_break_duration": 30,
    }
    assert StaffSettings.objects.count() == 1
    assert outbox() == [(events.SETTINGS_UPDATED, A.key, {})]


def test_hours_are_stored_without_seconds_and_a_second_save_updates_the_same_row():
    run("staff.settings.update", SettingsIn(default_work_start="07:30:45"))
    settings = run("staff.settings.update", SettingsIn(default_break_duration=45))
    row = StaffSettings.objects.get()
    assert (
        row.default_work_start,
        row.default_break_duration,
        settings.default_work_start,
    ) == (dt.time(7, 30), 45, "07:30")


def test_saving_the_same_settings_announces_nothing():
    run("staff.settings.update", SettingsIn(default_break_duration=30))
    OutboxEvent.objects.all().delete()
    run("staff.settings.update", SettingsIn(default_break_duration=30))
    update_settings(ctx_for(), SettingsIn(default_work_start="09:00:30"))  # stored without seconds: the same
    assert outbox() == []


def test_an_employee_does_not_change_the_settings():
    with pytest.raises(PermissionDenied):
        run("staff.settings.update", SettingsIn(default_break_duration=30), "hub_employee")


# The default working day proposes the week of a new schedule (STAFF-F13), and a schedule's day never
# crosses midnight: the working day ends after it starts and its break is shorter than the day.


def refused_settings(data, saved=None):
    if saved is not None:
        StaffSettings.objects.create(**saved)
    with pytest.raises(InvalidPayload) as excinfo:
        run("staff.settings.update", data)
    return excinfo.value.fields


def test_a_working_day_that_ends_before_it_starts_is_refused_under_its_end():
    assert refused_settings(SettingsIn(default_work_start="22:00", default_work_end="06:00")) == {
        "default_work_end": "The start time must be before the end time."
    }
    assert refused_settings(SettingsIn(default_work_end="09:00")) == {
        "default_work_end": "The start time must be before the end time."
    }
    assert not StaffSettings.objects.exists() and outbox() == []


def test_a_start_after_the_saved_end_is_refused_under_the_start():
    fields = refused_settings(
        SettingsIn(default_work_start="19:00"),
        saved={"default_work_start": dt.time(9), "default_work_end": dt.time(18)},
    )
    assert fields == {"default_work_start": "The start time must be before the end time."}
    assert StaffSettings.objects.get().default_work_start == dt.time(9)
    assert outbox() == []


def test_a_night_shift_saved_before_the_rule_is_refused_under_the_start_whatever_is_changed():
    # A working day saved when a night shift was still admitted cannot propose a schedule's day:
    # changing only the break says so under the start (nothing of the day was sent), and saves nothing.
    fields = refused_settings(
        SettingsIn(default_break_duration=30),
        saved={"default_work_start": dt.time(22), "default_work_end": dt.time(6)},
    )
    assert fields == {"default_work_start": "The start time must be before the end time."}
    assert StaffSettings.objects.get().default_break_duration == 60
    assert outbox() == []


def test_the_break_must_be_shorter_than_the_working_day():
    message = {"default_break_duration": "The break must fall inside the working hours."}
    assert refused_settings(SettingsIn(default_work_start="09:00", default_work_end="10:00", default_break_duration=60)) == message
    # A day shortened under the saved break: the break is what no longer fits.
    StaffSettings.objects.all().delete()
    assert refused_settings(SettingsIn(default_work_end="09:30"), saved={"default_break_duration": 30}) == message
    StaffSettings.objects.all().delete()
    settings = run(
        "staff.settings.update",
        SettingsIn(default_work_start="09:00", default_work_end="10:00", default_break_duration=59),
    )
    assert (settings.default_work_end, settings.default_break_duration) == ("10:00", 59)
