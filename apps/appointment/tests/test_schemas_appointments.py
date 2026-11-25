"""One appointment: it is named by its id or its number."""

from apps.appointment.schemas.appointments import AppointmentRefIn

from .schema_checks import ID, errors


def test_an_appointment_is_named_by_its_id_or_its_number():
    assert not errors(AppointmentRefIn, id=ID)
    assert not errors(AppointmentRefIn, number="APT-20261019-0001")
    assert "number" in errors(AppointmentRefIn)
