"""The settings of Appointments as they are read."""

from apps.appointment.models import Appointment, Settings
from apps.appointment.queries.settings import settings_out
from apps.appointment.schemas.settings import SettingsOut

from .conftest import HUB_DB, make_settings, run

pytestmark = HUB_DB


def test_the_settings_answer_every_datum_of_their_schema():
    assert set(settings_out(Settings())) == set(SettingsOut.model_fields)


def test_the_settings_are_the_factory_ones_until_saved_with_the_business_zone():
    out = run("appointment.settings.get")
    assert (out.default_duration, out.allow_overlapping, out.timezone) == (
        60,
        True,
        "Europe/Madrid",
    )
    make_settings(slot_interval=20)
    assert run("appointment.settings.get").slot_interval == 20
    assert Appointment.objects.count() == 0
