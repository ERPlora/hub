"""The agenda's lanes: who takes bookings, and who else keeps appointments those days."""

from apps.appointment.queries.lanes import takes_bookings

from .conftest import HUB_DB, MONDAY, TUESDAY, as_ctx, at, employee_linked_to, make_appointment, make_member, run

pytestmark = HUB_DB


def test_only_an_active_bookable_professional_takes_bookings(salon):
    away = make_member("Dani", "Ortiz", status="on_leave")
    desk = make_member("Carla", "Sanz", is_bookable=False)
    assert [takes_bookings(member) for member in (salon.ana, away, desk)] == [True, False, False]


def test_the_lanes_are_the_bookable_team_then_who_keeps_appointments_and_the_unassigned(
    salon,
):
    salon.bea.is_bookable = False
    salon.bea.save()
    carla = make_member("Carla", "Sanz", status="inactive")
    make_member("Dani", "Ortiz", status="on_leave")
    make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "10:00"))
    make_appointment(salon.lucia, carla, [salon.cut], at(MONDAY, "11:00"))
    make_appointment(salon.lucia, None, [salon.cut], at(MONDAY, "12:00"))
    lanes = run("appointment.agenda.lanes", {"date_from": MONDAY})
    assert [(lane.name, lane.takes_bookings) for lane in lanes.rows] == [
        ("Ana López", True),
        ("Bea Ruiz", False),
        ("Carla Sanz", False),
    ]
    assert (lanes.unassigned, lanes.sees_everyone) == (1, True)
    # Another day, nobody keeps a lane.
    assert [
        lane.name
        for lane in run("appointment.agenda.lanes", {"date_from": TUESDAY}).rows
    ] == ["Ana López"]


def test_an_employees_lanes_are_their_own(salon, make_user):
    ctx = employee_linked_to(salon.bea, make_user)
    lanes = as_ctx(ctx, "appointment.agenda.lanes", {"date_from": MONDAY})
    assert ([lane.staff_id for lane in lanes.rows], lanes.own_staff_id) == (
        [salon.bea.id],
        salon.bea.id,
    )
