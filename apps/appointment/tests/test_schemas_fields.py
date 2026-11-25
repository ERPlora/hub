"""What the schemas of Appointments share: a list pages by at most 100 and an input refuses what it does not have."""

from apps.appointment.schemas.agenda import AppointmentListIn
from apps.appointment.schemas.fields import PageIn

from .schema_checks import MONDAY, errors


def test_a_page_is_one_to_a_hundred_rows_and_refuses_an_unknown_filter():
    assert PageIn().limit == 50
    assert errors(PageIn, limit=0) and errors(PageIn, limit=101)
    assert "colour" in errors(AppointmentListIn, date_from=MONDAY, colour="red")
