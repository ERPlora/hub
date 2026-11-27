"""The settings (SCHEDULE-F08, F09): the defaults until saved, with the business's time zone."""

from apps.schedule.models import ScheduleSettings

from .conftest import HUB_DB
from .test_queries import run

pytestmark = HUB_DB


def test_the_settings_are_the_defaults_until_saved_with_the_business_zone():
    settings = run("schedule.settings.get")
    assert (settings.week_starts_on, settings.hours_confirmed, settings.timezone) == (
        1,
        False,
        "Europe/Madrid",
    )
    ScheduleSettings.objects.create(week_starts_on=7)
    assert run("schedule.settings.get").week_starts_on == 7
