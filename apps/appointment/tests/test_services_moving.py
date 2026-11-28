"""Moving and editing an appointment (APPOINTMENT-F04, APPOINTMENT-F06, APPOINTMENT-F22)."""

import uuid

import pytest
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from apps.appointment.models.appointments import Appointment, History

from .conftest import HUB_DB, MONDAY, assign, at, ctx_for, make_appointment, make_customer, run, wall
from .write_checks import actions, book, events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_moving_keeps_the_number_and_writes_the_change(salon):
    out = book(salon, "10:00")
    moved = run(
        "appointment.appointment.reschedule",
        {"number": out.number, "start": wall(MONDAY, "10:15")},
    )
    assert (moved.number, moved.start) == (out.number, at(MONDAY, "10:15"))
    line = History.objects.filter(appointment_id=out.id, action="rescheduled").get()
    assert line.new_value["start"].startswith(f"{MONDAY.isoformat()}T10:15")
    assert len(events("appointment.appointment.rescheduled")) == 1


def test_handing_over_keeps_the_price_and_changing_services_brings_the_catalogs(salon):
    assign(salon.cut, salon.bea, price=9000)
    assign(salon.cut, salon.ana)
    out = book(salon, "10:00", staff_id=str(salon.bea.id))
    assert out.total == 9000
    handed = run(
        "appointment.appointment.reschedule", {"id": str(out.id), "staff": "Ana"}
    )
    assert (handed.staff_name, handed.total) == ("Ana López", 9000)
    changed = run(
        "appointment.appointment.reschedule",
        {"id": str(out.id), "services": [{"service": "Colour"}]},
    )
    assert (changed.service_names, changed.total, changed.duration_minutes) == (
        "Colour",
        4500,
        60,
    )
    assert actions(out.id) == ["created", "staff_changed", "service_changed"]


def test_only_a_pending_or_confirmed_uncharged_appointment_moves(salon):
    for status in ("in_progress", "completed", "cancelled", "no_show"):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status=status
        )
        refused(
            "appointment.cannot_reschedule",
            lambda item=item: run(
                "appointment.appointment.reschedule",
                {"id": str(item.id), "start": wall(MONDAY, "15:00")},
            ),
        )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.cannot_reschedule",
        lambda: run(
            "appointment.appointment.reschedule",
            {"id": str(charged.id), "start": wall(MONDAY, "15:00")},
        ),
    )


def test_the_customer_moves_only_her_own_appointment_and_keeps_the_notice(salon):
    out = book(salon, "10:00")
    other = make_customer("Pepa Gil", phone="+34600222333")
    refused(
        "appointment.appointment_not_found",
        lambda: run(
            "appointment.appointment.reschedule",
            {
                "id": str(out.id),
                "start": wall(MONDAY, "12:00"),
                "on_behalf_of_customer": True,
                "customer_id": str(other.id),
            },
        ),
        NotFound,
    )
    moved = run(
        "appointment.appointment.reschedule",
        {
            "id": str(out.id),
            "start": wall(MONDAY, "12:00"),
            "on_behalf_of_customer": True,
            "customer": "+34600111222",
            "reason": "Work",
        },
    )
    assert moved.start == at(MONDAY, "12:00")
    line = History.objects.get(appointment_id=out.id, action="rescheduled")
    # Marked as the customer's, and who in the team wrote it down stays.
    assert (line.by_customer, line.reason, line.actor) == (True, "Work", "tester")


def test_on_the_customers_behalf_an_employee_still_changes_only_her_own_agenda(salon, make_user):
    user = make_user("bea", role="hub_employee")
    salon.bea.user = user.person
    salon.bea.save()
    assign(salon.cut, salon.bea)
    assign(salon.cut, salon.ana)
    own = run(
        "appointment.appointment.create",
        {"customer_id": str(salon.lucia.id), "services": [{"service_id": str(salon.cut.id)}], "staff_id": str(salon.bea.id), "start": wall(MONDAY, "10:00")},
    )
    move = get("appointment.appointment.reschedule")
    asked = {"id": str(own.id), "on_behalf_of_customer": True, "customer_id": str(salon.lucia.id)}
    with pytest.raises(PermissionDenied):
        move(ctx_for("hub_employee", actor=user), move.input.model_validate({**asked, "staff_id": str(salon.ana.id)}))
    assert Appointment.objects.get(pk=own.id).staff_id == salon.bea.id
    moved = move(ctx_for("hub_employee", actor=user), move.input.model_validate({**asked, "start": wall(MONDAY, "11:00")}))
    assert moved.start == at(MONDAY, "11:00")
    assert History.objects.get(appointment_id=own.id, action="rescheduled").actor == "bea"


def test_editing_notes_or_contact_writes_only_that(salon):
    out = book(salon)
    edited = run(
        "appointment.appointment.update",
        {"id": str(out.id), "notes": "Bring photo", "customer_phone": "600 999 888"},
    )
    assert (edited.notes, edited.customer_phone, edited.start) == (
        "Bring photo",
        "+34600999888",
        out.start,
    )
    assert actions(out.id) == ["created"]
    assert len(events("appointment.appointment.updated")) == 1
    error = refused(
        "appointment.phone_invalid",
        lambda: run(
            "appointment.appointment.update",
            {"id": str(out.id), "customer_phone": "12"},
        ),
        InvalidPayload,
    )
    assert "customer_phone" in error.fields
    moved = run(
        "appointment.appointment.update",
        {"id": str(out.id), "start": wall(MONDAY, "12:00"), "internal_notes": "x"},
    )
    assert (moved.start, moved.internal_notes) == (at(MONDAY, "12:00"), "x")
    assert actions(out.id)[-1] == "rescheduled"


def test_the_notes_of_an_appointment_the_agenda_cannot_edit_still_change(salon):
    # F22: «Edit» is only on a pending or confirmed one not charged; the notes of any other one (done,
    # cancelled, no-show, charged…) still change through the same operation, e.g. from the assistant.
    others = [
        make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status=status)
        for status in ("in_progress", "completed", "cancelled", "no_show")
    ]
    others.append(
        make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), sale_id=uuid.uuid7()
        )
    )
    for appointment in others:
        edited = run(
            "appointment.appointment.update",
            {"id": str(appointment.id), "notes": "Colour 6.1", "internal_notes": "Pays cash"},
        )
        assert (edited.status, edited.notes, edited.internal_notes) == (
            appointment.status,
            "Colour 6.1",
            "Pays cash",
        )
    assert len(events("appointment.appointment.updated")) == len(others)
