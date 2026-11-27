"""One appointment: how it is found and how it is read."""

import datetime as dt

import pytest
from live.errors import NotFound

from apps.appointment.models.appointments import Appointment
from apps.appointment.queries.reads import find_appointment

from .conftest import (
    HUB_DB,
    MONDAY,
    as_ctx,
    at,
    ctx_for,
    employee_linked_to,
    make_appointment,
    run,
    wall,
)

pytestmark = HUB_DB


def test_an_appointment_is_found_by_its_number_in_any_case(salon):
    appointment = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), number="APT-X-0001")
    assert find_appointment(ctx_for(), None, "apt-x-0001") == appointment


def test_an_appointment_is_read_by_its_id_or_its_number_with_contact_and_notes(salon):
    appointment = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        number="APT-20261019-0007",
        internal_notes="7/1",
    )
    by_number = run("appointment.appointment.get", {"number": "APT-20261019-0007"})
    assert (by_number.id, by_number.customer_phone, by_number.internal_notes) == (
        appointment.id,
        "+34600111222",
        "7/1",
    )
    with pytest.raises(NotFound) as missing:
        run("appointment.appointment.get", {"number": "APT-NOPE"})
    assert missing.value.code == "appointment.appointment_not_found"


def test_an_employee_cannot_read_a_colleagues_appointment(salon, make_user):
    theirs = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    ctx = employee_linked_to(salon.bea, make_user)
    with pytest.raises(NotFound):
        as_ctx(ctx, "appointment.appointment.get", {"id": str(theirs.id)})


# A flow's template prints a value as it comes, with no clock nor formatter: an
# automation confirming a booking says «el martes a las 10:30» because the appointment gives its day and its
# hour ready to read, in the language of whoever asks, on the business's clock (24 hours, as the old
# product's messages; the year kept: a booking can be months away).
def test_an_appointment_gives_its_day_and_hour_ready_to_read_in_the_callers_language(salon):
    tuesday = dt.date(2030, 3, 5)
    late = make_appointment(salon.lucia, salon.ana, [salon.cut], at(tuesday, "00:30"))
    spanish = run("appointment.appointment.get", {"id": str(late.id)}, language="es")
    assert (spanish.start_date_label, spanish.start_time_label) == ("martes, 5 de marzo de 2030", "00:30")
    english = run("appointment.appointment.get", {"id": str(late.id)}, language="en")
    assert (english.start_date_label, english.start_time_label) == ("Tuesday, March 5, 2030", "00:30")
    booked = run(
        "appointment.appointment.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "start": wall(MONDAY, "16:05"),
        },
        language="es",
    )
    assert booked.start_time_label == "16:05" and booked.start_date_label.startswith("lunes, ")


def test_an_appointment_says_the_words_a_card_names_it_by(salon):
    # hub#634: whoever says yes to cancelling it reads whose it is, when and with whom, never its id.
    late = make_appointment(salon.lucia, salon.ana, [salon.cut], at(dt.date(2030, 3, 5), "10:30"))
    said = run("appointment.appointment.get", {"id": str(late.id)}, language="es")
    assert said.label == f"{salon.lucia.name} · martes, 5 de marzo de 2030 · 10:30 · {said.staff_name}"


def test_the_words_of_an_appointment_leave_out_what_it_no_longer_has(salon):
    # Her data erased (the name goes) and its professional gone: no empty piece between the separators.
    late = make_appointment(salon.lucia, salon.ana, [salon.cut], at(dt.date(2030, 3, 5), "10:30"))
    Appointment.objects.filter(pk=late.id).update(customer_name="", staff_name="", staff=None)
    assert run("appointment.appointment.get", {"id": str(late.id)}).label == "Tuesday, March 5, 2030 · 10:30"
