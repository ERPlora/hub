"""Appointments with the real Staff app: the professionals, their weekly schedule and their approved time
off are Staff's, written by Staff's own operations; the agenda reads them through
``staff.availability.for_member`` and reacts to a professional leaving (``staff.member.terminated``).
"""

import datetime as dt

import pytest
from live.errors import Conflict
from live.models import OutboxEvent

from apps.appointment import events
from apps.appointment.models import Appointment

from .conftest import A, MONDAY, at, make_customer, make_service, make_tax, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


@pytest.fixture
def cast(db):
    cut = make_service("Haircut", duration=30, tax=make_tax())
    lucia = make_customer("Lucía Pérez")
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    return cut, lucia, ana


def book(start: str, staff: str = "Ana López", **extra):
    return run(
        "appointment.appointment.create",
        {"customer": "Lucía Pérez", "services": [{"service": "Haircut"}], "staff": staff, "start": wall(MONDAY, start), **extra},
    )


def code_of(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    return refused.value.code


def test_the_professionals_weekly_schedule_from_staff_decides_her_hours(cast):
    run(
        "staff.schedule.create",
        {"member": "Ana López", "days": [{"weekday": 0, "start_time": "10:00", "end_time": "14:00", "break_start": "12:00", "break_end": "12:30"}]},
    )
    assert book("10:00").staff_name == "Ana López"
    assert code_of(lambda: book("12:00")) == "appointment.outside_staff_hours"
    assert code_of(lambda: book("09:30")) == "appointment.outside_staff_hours"
    slots = run("appointment.availability.slots", {"date": MONDAY, "services": ["Haircut"], "staff": "Ana López"})
    assert "12:00" not in [f"{slot.start:%H:%M}" for slot in slots.slots]


def test_approved_time_off_refuses_and_a_pending_one_does_not(cast):
    request = run("staff.time_off.create", {"member": "Ana López", "start_date": MONDAY.isoformat(), "end_date": MONDAY.isoformat()})
    assert book("10:00").status == "confirmed"
    run("staff.time_off.approve", {"id": str(request.id)})
    assert code_of(lambda: book("11:00")) == "appointment.outside_staff_hours"


def test_a_deactivated_professional_keeps_her_appointments_and_takes_no_new_ones(cast):
    _cut, _lucia, ana = cast
    booked = book("10:00")
    run("staff.member.deactivate", {"id": str(ana.id)})
    assert code_of(lambda: book("11:00")) == "appointment.staff_not_bookable"
    lanes = run("appointment.agenda.lanes", {"date_from": MONDAY})
    assert [(lane.name, lane.takes_bookings) for lane in lanes.rows] == [("Ana López", False)]
    assert Appointment.objects.get(pk=booked.id).staff_id == ana.id


def test_a_professional_who_leaves_unassigns_her_upcoming_appointments(cast):
    _cut, _lucia, ana = cast
    booked = book("10:00")
    run("staff.member.terminate", {"id": str(ana.id)})
    event = OutboxEvent.objects.filter(name="staff.member.terminated").latest("id")
    assert events.react(A, event.name, event.payload).changed == 1
    item = run("appointment.appointment.get", {"id": str(booked.id)})
    assert (item.staff_id, item.staff_name) == (None, "Ana López")
    assert run("appointment.appointment.list", {"date_from": MONDAY, "unassigned": True}).total == 1
    bea = run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    handed = run("appointment.appointment.reschedule", {"id": str(booked.id), "staff_id": str(bea.id)})
    assert (handed.staff_name, handed.start) == ("Bea Ruiz", at(MONDAY, "10:00"))
