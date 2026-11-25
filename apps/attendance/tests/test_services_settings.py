"""The time clock settings: attendance.settings.update."""

import pytest
from live.errors import InvalidPayload, PermissionDenied

from apps.attendance import events
from apps.attendance.models import AttendanceSettings
from apps.attendance.schemas import SettingsOut

from .conftest import HUB_DB, WORKPLACE, names, run

pytestmark = HUB_DB


# attendance.settings.update (ATTENDANCE-F04)


def test_the_first_save_creates_the_settings_and_only_what_is_sent_changes(clock):
    clock("2026-10-06T07:00")
    saved = run("attendance.settings.update", {"auto_close_after_hours": 10})
    assert isinstance(saved, SettingsOut)
    assert (
        saved.auto_close_after_hours,
        saved.geofence_radius_m,
        saved.require_location,
        saved.saved,
    ) == (10, 100, False, True)
    run(
        "attendance.settings.update",
        {
            "require_location": True,
            "workplace_lat": WORKPLACE[0],
            "workplace_lng": WORKPLACE[1],
            "geofence_radius_m": 250,
        },
    )
    row = AttendanceSettings.objects.get()
    assert (
        row.auto_close_after_hours,
        row.require_location,
        row.geofence_radius_m,
        row.workplace_lat,
    ) == (10, True, 250, WORKPLACE[0])
    assert names() == [events.SETTINGS_UPDATED, events.SETTINGS_UPDATED]


def test_saving_nothing_new_says_nothing(clock):
    clock("2026-10-06T07:00")
    run("attendance.settings.update", {"auto_close_after_hours": 10})
    run("attendance.settings.update", {"auto_close_after_hours": 10})
    assert names() == [events.SETTINGS_UPDATED]


def test_the_workplace_is_both_coordinates_or_neither(clock):
    clock("2026-10-06T07:00")
    run(
        "attendance.settings.update",
        {"workplace_lat": WORKPLACE[0], "workplace_lng": WORKPLACE[1]},
    )
    with pytest.raises(InvalidPayload) as caught:
        run("attendance.settings.update", {"workplace_lng": None})
    assert list(caught.value.fields) == ["workplace_lng"]
    cleared = run(
        "attendance.settings.update", {"workplace_lat": None, "workplace_lng": None}
    )
    assert (cleared.workplace_lat, cleared.workplace_set) == (None, False)


def test_an_employee_cannot_save_the_settings(person):
    _, ctx = person()
    with pytest.raises(PermissionDenied):
        run("attendance.settings.update", {"auto_close_after_hours": 3}, ctx)
    assert not AttendanceSettings.objects.exists()

