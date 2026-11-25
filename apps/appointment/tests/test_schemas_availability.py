"""Free times take a day and the services or the minutes."""

from apps.appointment.schemas.availability import CheckIn, SlotsIn

from .schema_checks import MONDAY, errors


def test_free_times_take_a_day_and_the_services_or_the_minutes():
    assert not errors(SlotsIn, date=MONDAY, services=["Cut"])
    assert not errors(SlotsIn, date=MONDAY, duration_minutes=45, staff="Ana")
    assert "__all__" in errors(SlotsIn, date=MONDAY)
    assert "__all__" in errors(CheckIn, start=f"{MONDAY}T10:00")
