"""Models of what an appointment and a series both keep: when each was created, changed and deleted, and who
created it."""

from apps.appointment.models.audit import Audited

from .conftest import HUB_DB, MONDAY, at, make_appointment, make_series

pytestmark = HUB_DB


def test_an_appointment_and_a_series_are_stamped_when_made_and_start_undeleted(salon):
    appointment = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    series = make_series(salon)
    assert Audited._meta.abstract
    for row in (appointment, series):
        assert isinstance(row, Audited)
        assert (row.created_at is not None, row.updated_at is not None) == (True, True)
        assert (row.deleted_at, row.created_by) == (None, "")
