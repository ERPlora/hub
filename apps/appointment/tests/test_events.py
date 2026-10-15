"""Events of the appointment app and its reactions to the events of Customers, Staff and Sales.

The reactions are handed the real payloads, read back from the outbox where each app's own operation
recorded them (as the relay of phase 2 will), and run as the system; repeating one changes nothing.
"""

import datetime as dt
import uuid

import pytest
from live.models import OutboxEvent

from apps.appointment import events
from apps.appointment.models import Appointment, History, Recurring, RecurringService

from .conftest import A, MONDAY, at, make_appointment, run

pytestmark = pytest.mark.django_db


def relay(name: str):
    """Hands the last ``name`` event of the outbox to the appointment app's reactions."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    return events.react(A, event.name, event.payload)


def test_every_event_is_named_app_entity_fact():
    for name in events.ALL:
        app, entity, fact = name.split(".")
        assert app == "appointment" and entity and fact, name
    assert len(set(events.ALL)) == len(events.ALL)


def test_the_reactions_are_the_workbooks():
    assert events.REACTIONS == {
        "customer.customer.merged": "appointment.customer.reassign",
        "customer.customer.erased": "appointment.customer.erase",
        "staff.member.terminated": "appointment.staff.release",
        "sale.sale.created_from_appointment": "appointment.appointment.mark_charged",
        "sale.sale.voided": "appointment.appointment.unmark_charged",
        "sale.order.voided": "appointment.appointment.release_check",
    }


def test_an_event_without_a_reaction_is_ignored():
    assert (
        events.react(A, "service.service.archived", {"id": str(uuid.uuid7())}) is None
    )


def test_merging_two_cards_moves_the_appointments_and_series_to_the_one_that_stays(
    salon,
):
    from .conftest import make_customer

    twin = make_customer("Lucia Perez", phone="+34600999000")
    booked = make_appointment(twin, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    series = Recurring.objects.create(
        customer=twin,
        customer_name=twin.name,
        staff=salon.ana,
        frequency="weekly",
        time=dt.time(10),
        duration_minutes=30,
        start_date=MONDAY,
    )
    run(
        "customer.customer.merge",
        {"id": str(salon.lucia.id), "absorbed_id": str(twin.id)},
    )
    assert relay("customer.customer.merged").changed == 2
    booked.refresh_from_db()
    series.refresh_from_db()
    assert (booked.customer_id, series.customer_id) == (salon.lucia.id, salon.lucia.id)
    # The name it was booked with is a photo of that moment.
    assert booked.customer_name == "Lucia Perez"
    assert relay("customer.customer.merged").changed == 0


def test_erasing_a_customer_empties_her_copies_and_pauses_her_series(salon):
    booked = make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(MONDAY, "10:00"),
        notes="Bring photo",
        internal_notes="allergic",
        cancellation_reason="ill",
    )
    History.objects.create(
        appointment=booked,
        action="created",
        new_value={"customer_name": "Lucía Pérez", "x": 1},
    )
    History.objects.create(appointment=booked, action="cancelled", reason="She is ill")
    series = Recurring.objects.create(
        customer=salon.lucia,
        customer_name="Lucía Pérez",
        staff=salon.ana,
        frequency="weekly",
        time=dt.time(10),
        duration_minutes=30,
        start_date=MONDAY,
    )
    RecurringService.objects.create(recurring=series, service=salon.cut)
    run(
        "customer.customer.erase", {"id": str(salon.lucia.id), "reason": "GDPR request"}
    )
    assert relay("customer.customer.erased").changed == 2
    booked.refresh_from_db()
    series.refresh_from_db()
    assert (
        booked.customer_name,
        booked.customer_phone,
        booked.notes,
        booked.internal_notes,
    ) == ("", "", "", "")
    assert (
        booked.cancellation_reason == "" and booked.number and booked.lines.count() == 1
    )
    assert (series.customer_name, series.is_active) == ("", False)
    assert [line.reason for line in booked.history.all()] == ["", ""]
    assert booked.history.get(action="created").new_value == {"x": 1}
    assert relay("customer.customer.erased").changed == 0


def test_a_professional_who_leaves_hands_her_upcoming_appointments_to_nobody_and_pauses_her_series(
    salon,
):
    upcoming = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")
    )
    done = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), status="completed"
    )
    series = Recurring.objects.create(
        customer=salon.lucia,
        customer_name="Lucía",
        staff=salon.ana,
        frequency="weekly",
        time=dt.time(10),
        duration_minutes=30,
        start_date=MONDAY,
    )
    run("staff.member.terminate", {"id": str(salon.ana.id)})
    assert relay("staff.member.terminated").changed == 2
    upcoming.refresh_from_db()
    done.refresh_from_db()
    series.refresh_from_db()
    assert (upcoming.staff_id, upcoming.staff_name, done.staff_id) == (
        None,
        "Ana López",
        salon.ana.id,
    )
    assert upcoming.history.get().action == "unassigned"
    assert (series.staff_id, series.is_active) == (None, False)
    assert (
        OutboxEvent.objects.filter(name="appointment.appointment.unassigned").count()
        == 1
    )
    assert run("appointment.agenda.lanes", {"date_from": MONDAY}).unassigned == 1


def test_charged_and_voided_sales_come_back_as_their_payload_says(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    sale = uuid.uuid7()
    out = events.react(
        A,
        "sale.sale.created_from_appointment",
        {
            "sale_id": str(sale),
            "appointment_id": str(booked.id),
            "staff_id": None,
            "total": 2000,
        },
    )
    assert out.changed == 1
    assert Appointment.objects.get(pk=booked.pk).sale_id == sale
    voided = {
        "sale_id": str(sale),
        "sale_number": "T-1",
        "reason": "x",
        "voided_by": "y",
        "total": 2000,
    }
    assert events.react(A, "sale.sale.voided", voided).changed == 1
    assert Appointment.objects.get(pk=booked.pk).sale_id is None
