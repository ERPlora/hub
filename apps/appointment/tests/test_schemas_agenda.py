"""The agenda reads a short range of days."""

from apps.appointment.schemas.agenda import AppointmentListIn

from .schema_checks import MONDAY, errors


def test_the_agenda_reads_a_short_range():
    assert not errors(AppointmentListIn, date_from=MONDAY, date_to="2026-12-19")
    assert "date_to" in errors(
        AppointmentListIn, date_from=MONDAY, date_to="2026-10-18"
    )
    assert "date_to" in errors(
        AppointmentListIn, date_from=MONDAY, date_to="2027-01-19"
    )
