"""Who reads and changes what in Appointments: what a caller that is not a person never reads."""

import pytest

from apps.appointment.queries.access import PRIVATE, for_caller
from base.sensitive import DATA_PERMISSIONS

from .conftest import HUB_DB, MONDAY, at, ctx_for, make_appointment, run

pytestmark = HUB_DB


def test_what_is_private_reads_empty_to_a_caller_that_is_not_a_person_and_the_rest_whole():
    answer = {"number": "APT-1", **dict.fromkeys(PRIVATE, "kept")}
    assert for_caller(ctx_for(), answer) == answer
    assert for_caller(ctx_for(actor="system"), answer) == {"number": "APT-1", **dict.fromkeys(PRIVATE, "")}


# A model reading a stranger's message (a flow's step gets every
# read of the app, and the data permissions of base) composes these reads: what is the salon's (its notes, a cancellation's reason) and the
# customer's contact never reach a caller that is not a person. The team, and its assistant with the person's
# own session, read them; the day's agenda carries neither, for anybody.
@pytest.mark.parametrize("actor", ["flow_run:0190a1b2", "system", None])
def test_a_caller_who_is_not_a_person_reads_a_visit_without_the_salons_notes_nor_the_contact(salon, actor):
    from apps.appointment.apps import AppointmentConfig

    salon.lucia.email = "lucia@example.com"
    booked = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        notes="Bring photo",
        internal_notes="7/1 + 6%",
        cancellation_reason="Allergy",
    )
    reads = {p for p in AppointmentConfig.permissions if p.split(".", 1)[-1].startswith("view")}
    automation = {"actor": actor, "permissions": reads | DATA_PERMISSIONS}
    got = run("appointment.appointment.get", {"number": booked.number}, **automation)
    assert got.number == booked.number and got.customer_name == "Lucía Pérez"
    private = ("customer_phone", "customer_email", "notes", "internal_notes", "cancellation_reason")
    assert {name: getattr(got, name) for name in private} == dict.fromkeys(private, "")
    visits = run("appointment.appointment.list_for_customer", {"customer_id": str(salon.lucia.id)}, **automation)
    assert [(visit.id, visit.notes, visit.internal_notes) for visit in visits.rows] == [(booked.id, "", "")]
    person = run("appointment.appointment.get", {"number": booked.number})
    assert (person.customer_phone, person.internal_notes, person.cancellation_reason) == (
        "+34600111222",
        "7/1 + 6%",
        "Allergy",
    )
    agenda = run("appointment.appointment.list", {"date_from": MONDAY.isoformat()})
    assert not set(agenda.rows[0].model_dump()) & set(private)
