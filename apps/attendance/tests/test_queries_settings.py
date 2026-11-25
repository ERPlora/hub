"""The time clock settings as they read (attendance.settings.get): the defaults until the business saves its own."""

from apps.attendance.models import AttendanceSettings
from apps.attendance.schemas import SettingsOut

from .conftest import HUB_DB, run

pytestmark = HUB_DB


# attendance.settings.get


def test_the_settings_are_the_defaults_until_saved(person):
    _, ctx = person()
    defaults = run("attendance.settings.get", {}, ctx)
    assert isinstance(defaults, SettingsOut)
    assert (
        defaults.require_location,
        defaults.geofence_radius_m,
        defaults.auto_close_after_hours,
    ) == (False, 100, 12)
    assert (defaults.workplace_set, defaults.saved, defaults.updated_at) == (
        False,
        False,
        None,
    )
    AttendanceSettings.objects.create(
        require_location=True, workplace_lat=40.4, workplace_lng=-3.7
    )
    saved = run("attendance.settings.get", {}, ctx)
    assert (saved.require_location, saved.workplace_set, saved.saved) == (
        True,
        True,
        True,
    )
