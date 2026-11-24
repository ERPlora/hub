"""The default working day a new schedule proposes (STAFF-F22)."""

import datetime as dt

from apps.staff.models import StaffSettings
from apps.staff.queries.settings import get_settings
from apps.staff.schemas.settings import SettingsGetIn

from .conftest import HUB_DB, ctx_for, run

pytestmark = HUB_DB


def test_settings_are_the_defaults_until_the_first_save():
    # Only the default working day: the other eight old settings changed nothing and are retired.
    assert run("staff.settings.get", SettingsGetIn(), "hub_employee").model_dump() == {
        "default_work_start": "09:00",
        "default_work_end": "18:00",
        "default_break_duration": 60,
    }
    assert not StaffSettings.objects.exists()  # a read never creates the row


def test_saved_settings_show_their_hours_as_hh_mm():
    StaffSettings.objects.create(default_work_start=dt.time(9, 30, 15), default_break_duration=30, max_daily_hours=8)
    settings = get_settings(ctx_for(), SettingsGetIn())
    assert settings.model_dump() == {"default_work_start": "09:30", "default_work_end": "18:00", "default_break_duration": 30}
