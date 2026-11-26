"""The settings (SCHEDULE-F08): the first save creates them, only a change says so, and the week's confirmation is
never touched."""

from apps.schedule.models import ScheduleSettings
from apps.schedule.schemas.settings import SettingsIn

from .conftest import HUB_DB
from .test_services import confirmed, names, run

pytestmark = HUB_DB


def test_the_first_save_of_the_settings_creates_them_and_a_change_says_so():
    ScheduleSettings.objects.all().delete()
    saved = run("schedule.settings.update", SettingsIn(week_starts_on=7))
    assert (saved.week_starts_on, saved.timezone) == (7, "Europe/Madrid")
    assert ScheduleSettings.objects.get().week_starts_on == 7
    assert names() == ["schedule.settings.updated"]
    run("schedule.settings.update", SettingsIn(week_starts_on=7))
    run("schedule.settings.update", SettingsIn())
    assert names() == ["schedule.settings.updated"]


def test_saving_the_settings_never_touches_the_confirmation():
    ScheduleSettings.objects.create(hours_confirmed=True)
    run("schedule.settings.update", SettingsIn(week_starts_on=1))
    assert confirmed()
