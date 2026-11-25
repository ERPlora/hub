"""What a hub's database may hold: the platform's apps, and every hub app now that each is portable."""

from base.tenancy.migrator import app_sets
from base.tenancy.tests.test_migrator import PLATFORM


def test_the_platform_is_what_every_hubs_database_has():
    assert set(app_sets.platform_apps()) == set(PLATFORM)


def test_every_hub_app_lives_in_a_hubs_database_now_that_its_people_are_its_own():
    """The apps that linked control's user hang from ``base.HubUser`` now, so every hub app, and what waited for them
    (service, appointment, online_booking), fits a hub's database."""
    portable = set(app_sets.portable_apps())

    assert {"staff", "attendance", "task", "whatsapp_inbox", "service", "appointment", "online_booking"} <= portable
    assert portable == set(app_sets.hub_apps())

