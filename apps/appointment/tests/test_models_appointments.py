"""Models of the appointments, their services and their history: what the database itself refuses, and what a row looks like.

The operations check before writing; these constraints are the last line when two writes race or a
second write path (the admin) skips the rules.
"""

import datetime as dt
import uuid

from apps.appointment.models.appointments import Appointment, AppointmentService, History
from apps.appointment.models.series import Recurring

from .conftest import (
    HUB_DB,
    MONDAY,
    at,
    make_appointment,
    make_customer,
    make_member,
    make_service,
    refused,
)

pytestmark = HUB_DB


def test_every_key_is_a_uuid7():
    customer, ana, cut = make_customer(), make_member(), make_service()
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    assert isinstance(appointment.id, uuid.UUID) and appointment.id.version == 7
    assert appointment.lines.get().id.version == 7


def test_an_appointment_ends_after_it_starts_and_its_number_is_unique():
    customer, ana, cut = make_customer(), make_member(), make_service()
    first = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"), number="APT-1")
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "11:00"), number="APT-1"
        )
    )
    first.end = first.start
    refused(lambda: first.save())


def test_an_unknown_status_or_source_is_refused():
    customer, ana, cut = make_customer(), make_member(), make_service()
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "10:00"), status="lost"
        )
    )
    refused(
        lambda: make_appointment(
            customer, ana, [cut], at(MONDAY, "10:00"), source="fax"
        )
    )


def test_one_live_appointment_per_occurrence_of_a_series():
    customer, ana, cut = make_customer(), make_member(), make_service()
    series = Recurring.objects.create(
        customer=customer,
        customer_name=customer.name,
        staff=ana,
        staff_name=ana.full_name,
        frequency="weekly",
        day_of_week=0,
        time=dt.time(10),
        duration_minutes=30,
        start_date=MONDAY,
    )
    fields = {"recurring": series, "occurrence_date": MONDAY}
    first = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"), **fields)
    refused(
        lambda: make_appointment(customer, ana, [cut], at(MONDAY, "12:00"), **fields)
    )
    # A deleted occurrence frees its date (it is archived, not destroyed).
    first.deleted_at = first.start
    first.save()
    make_appointment(customer, ana, [cut], at(MONDAY, "12:00"), **fields)


def test_a_line_keeps_the_service_it_was_booked_with():
    customer, ana, cut = make_customer(), make_member(), make_service("Cut", price=1800)
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    line = appointment.lines.get()
    assert (line.name, line.price, line.duration_minutes, line.position) == (
        "Cut",
        1800,
        30,
        0,
    )
    refused(
        lambda: AppointmentService.objects.create(
            appointment=appointment,
            service=cut,
            name="Cut",
            price=1,
            duration_minutes=30,
            position=0,
        )
    )


def test_history_belongs_to_its_appointment():
    customer, ana, cut = make_customer(), make_member(), make_service()
    appointment = make_appointment(customer, ana, [cut], at(MONDAY, "10:00"))
    History.objects.create(appointment=appointment, action="created", actor="Ana")
    refused(lambda: History.objects.create(appointment=appointment, action="sneezed"))
    assert appointment.history.count() == 1


def test_a_row_reads_as_a_person_names_it():
    customer, ana, cut = (
        make_customer("Lucía"),
        make_member("Ana", "López"),
        make_service(),
    )
    appointment = make_appointment(
        customer, ana, [cut], at(MONDAY, "10:00"), number="APT-20261019-0001"
    )
    assert str(appointment) == "APT-20261019-0001"
    assert Appointment.Status.NO_SHOW == "no_show"
