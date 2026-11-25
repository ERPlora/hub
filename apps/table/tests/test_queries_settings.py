"""The room settings (``table.settings.get``): the factory ones until they are saved, with the business's time zone."""

import pytest

from .conftest import HUB_DB, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_the_settings_are_the_factory_ones_until_saved_and_say_the_business_zone():
    from apps.table.models import TableSettings

    assert run("table.settings.get", {}).model_dump() == {
        "prompt_guests_on_seat": True,
        "timer_warning_minutes": 60,
        "timer_critical_minutes": 90,
        "reserved_lead_minutes": 60,
        "timezone": "Europe/Madrid",
    }
    TableSettings.objects.create(prompt_guests_on_seat=False, timer_warning_minutes=30)
    assert run("table.settings.get", {}).timer_warning_minutes == 30
