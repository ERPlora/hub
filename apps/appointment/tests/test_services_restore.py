"""Restoring a deleted appointment (APPOINTMENT-F11, BASE-F114): the platform's own operation, run when ERPlora's staff
recover the business from a separate copy. The same appointment comes back to the agenda, with its number, its history
and its series, as long as it still fits it as a booking does; a refusal leaves no trace.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.appointment.models import Appointment, Counter, History
from apps.customer.models import Customer
from apps.service.models import Service
from apps.staff.models import Member

from .conftest import A, MONDAY, at, make_appointment, make_series, make_settings, run, wall

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]

RESTORE = "appointment.appointment.restore"


def restore(appointment_id, ctx=None):
    op = get(RESTORE)
    return op(ctx or system_context(A), op.input.model_validate({"id": str(appointment_id)}))


def book(salon, start="10:00", **extra):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "start": wall(MONDAY, start),
        **extra,
    }
    return run("appointment.appointment.create", data)


def deleted(salon, start="10:00", **extra):
    """An appointment booked by the agenda and deleted from it (APPOINTMENT-F11)."""
    out = book(salon, start, **extra)
    run("appointment.appointment.delete", {"id": str(out.id)})
    return Appointment.objects.get(pk=out.id)


def actions(appointment_id) -> list[str]:
    return list(History.objects.filter(appointment_id=appointment_id).order_by("at", "id").values_list("action", flat=True))


def outbox(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")]


def trace() -> tuple:
    return (
        list(Appointment.objects.order_by("id").values_list("id", "deleted_at")),
        History.objects.count(),
        OutboxEvent.objects.count(),
    )


def refused(code: str, appointment_id, error=Conflict):
    before = trace()
    with pytest.raises(error) as caught:
        restore(appointment_id)
    assert caught.value.code == code
    assert trace() == before


def test_the_same_appointment_comes_back_with_its_number_and_its_history_and_says_so(salon):
    gone = deleted(salon, notes="Bring the colour reference")
    numbers = list(Counter.objects.values_list("day", "last_number"))

    out = restore(gone.id)

    assert (out.id, out.number, out.status) == (gone.id, gone.number, "confirmed")
    back = Appointment.objects.get(pk=gone.id)
    assert (back.deleted_at, back.updated_by, back.notes) == (None, "system", "Bring the colour reference")
    assert actions(gone.id) == ["created", "deleted", "restored"]
    assert History.objects.get(appointment_id=gone.id, action="restored").actor == "system"
    # It keeps its number: none is taken for it.
    assert list(Counter.objects.values_list("day", "last_number")) == numbers
    assert outbox("appointment.appointment.restored") == [
        {
            "id": str(gone.id),
            "number": gone.number,
            "customer_id": str(salon.lucia.id),
            "staff_id": str(salon.ana.id),
            "start": gone.start.isoformat(),
        }
    ]
    assert [row.id for row in run("appointment.appointment.list", {"date_from": MONDAY}).rows] == [gone.id]


def test_one_of_a_series_comes_back_in_its_series_on_its_date(salon):
    series = make_series(salon)
    one = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), recurring=series, occurrence_date=MONDAY
    )
    run("appointment.appointment.delete", {"id": str(one.id)})

    restore(one.id)

    back = Appointment.objects.get(pk=one.id)
    assert (back.deleted_at, back.recurring_id, back.occurrence_date) == (None, series.id, MONDAY)


def test_one_still_waiting_for_the_business_comes_back_waiting(salon):
    make_settings(auto_confirm_online=False)
    gone = deleted(salon, source="online")
    assert gone.status == "pending"

    assert restore(gone.id).status == "pending"


def test_one_whose_time_was_taken_since_is_refused_with_why_and_nothing_is_written(salon):
    gone = deleted(salon)
    book(salon, "10:00")

    refused("appointment.slot_taken", gone.id)


def test_one_with_nobody_to_do_it_comes_back_with_nobody_judged_on_the_business_hours(salon):
    gone = deleted(salon)
    Appointment.objects.filter(pk=gone.id).update(staff=None, staff_name="")
    # Ana is busy then, but it is not hers any more.
    book(salon, "10:00")

    out = restore(gone.id)

    assert (out.id, out.staff_id) == (gone.id, None)


def test_a_cancelled_one_comes_back_cancelled_without_holding_its_time(salon):
    out = book(salon)
    run("appointment.appointment.cancel", {"id": str(out.id)})
    run("appointment.appointment.delete", {"id": str(out.id)})
    book(salon, "10:00")

    assert restore(out.id).status == "cancelled"
    assert actions(out.id) == ["created", "cancelled", "deleted", "restored"]


def test_one_whose_customer_the_business_no_longer_has_is_refused(salon):
    gone = deleted(salon)
    Customer.objects.filter(pk=salon.lucia.id).update(deleted_at=timezone.now())

    refused("customer.customer_unavailable", gone.id, NotFound)


def test_one_whose_professional_no_longer_takes_bookings_is_refused(salon):
    gone = deleted(salon)
    Member.objects.filter(pk=salon.ana.id).update(is_bookable=False)

    refused("appointment.staff_not_bookable", gone.id)


def test_one_whose_service_is_no_longer_bookable_is_refused(salon):
    gone = deleted(salon)
    Service.objects.filter(pk=salon.cut.id).update(is_active=False)

    refused("appointment.service_not_bookable", gone.id)


def test_one_whose_date_its_series_booked_again_is_refused(salon):
    series = make_series(salon)
    one = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), recurring=series, occurrence_date=MONDAY
    )
    run("appointment.appointment.delete", {"id": str(one.id)})
    make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(MONDAY, "12:00"), recurring=series, occurrence_date=MONDAY
    )

    refused("appointment.occurrence_booked", one.id)


def test_one_already_on_the_agenda_is_answered_as_it_is_and_nothing_is_written(salon):
    out = book(salon)
    before = trace()

    assert restore(out.id).id == out.id
    assert trace() == before


def test_one_the_business_does_not_have_is_not_found(salon):
    refused("appointment.appointment_not_found", uuid.uuid7(), NotFound)


def test_restoring_is_the_platforms_alone(salon):
    gone = deleted(salon)

    with pytest.raises(PermissionDenied):
        run(RESTORE, {"id": str(gone.id)}, role="hub_admin")
    assert Appointment.objects.get(pk=gone.id).deleted_at is not None


def test_it_is_judged_at_the_moment_it_is_restored(salon, monkeypatch):
    """An appointment whose time has come since it was deleted does not come back: the agenda books none in the past."""
    gone = deleted(salon)
    later = gone.start + dt.timedelta(hours=1)
    monkeypatch.setattr("django.utils.timezone.now", lambda: later.astimezone(dt.UTC))

    refused("appointment.in_past", gone.id)
