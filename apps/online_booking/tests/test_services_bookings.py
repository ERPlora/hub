"""The inbox's actions on an online booking: the diary does them, with this app's right and the diary's."""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.appointment.models.appointments import Appointment, History

from .conftest import HUB_DB, TUESDAY, at, events, make_appointment, run

pytestmark = HUB_DB


@pytest.fixture
def pending(salon):
    """Lucía's pending online booking of Tuesday 10:00 with Ana."""
    return make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        status="pending",
        number="APT-1",
    )


def test_confirming_a_booking_confirms_the_appointment(pending):
    answer = run("online_booking.booking.confirm", {"number": "APT-1"})
    assert answer.status == "confirmed"
    pending.refresh_from_db()
    assert pending.status == "confirmed"
    assert History.objects.filter(appointment=pending, action="confirmed").exists()
    assert [event["id"] for event in events("appointment.appointment.confirmed")] == [
        str(pending.id)
    ]


def test_a_booking_is_confirmed_as_a_person_says_it(pending):
    answer = run(
        "online_booking.booking.confirm",
        {"customer": "Lucía", "date": TUESDAY.isoformat()},
    )
    assert answer.number == "APT-1"


def test_confirming_twice_is_the_diarys_refusal(pending):
    run("online_booking.booking.confirm", {"number": "APT-1"})
    with pytest.raises(Conflict) as error:
        run("online_booking.booking.confirm", {"number": "APT-1"})
    assert error.value.code == "appointment.cannot_confirm"


def test_the_inbox_actions_need_this_apps_right_and_the_diarys(pending):
    with pytest.raises(PermissionDenied):
        run("online_booking.booking.confirm", {"number": "APT-1"}, role="hub_employee")
    with pytest.raises(PermissionDenied):
        run(
            "online_booking.booking.confirm",
            {"number": "APT-1"},
            permissions={"online_booking.confirm_booking", "appointment.view_appointment"},
        )
    assert Appointment.objects.get(pk=pending.pk).status == "pending"


def test_completing_marking_a_no_show_and_cancelling(salon, pending, clock):
    run("online_booking.booking.confirm", {"number": "APT-1"})
    assert (
        run(
            "online_booking.booking.complete", {"number": "APT-1"}, role="hub_manager"
        ).status
        == "completed"
    )

    other = make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "11:00"), number="APT-2"
    )
    with pytest.raises(Conflict) as error:
        run("online_booking.booking.no_show", {"number": "APT-2"})
    assert error.value.code == "appointment.no_show_too_early"
    clock.set(at(TUESDAY, "11:30"))
    assert (
        run("online_booking.booking.no_show", {"number": "APT-2"}).status == "no_show"
    )

    third = make_appointment(
        salon.lucia, salon.bea, [salon.cut], at(TUESDAY, "15:00"), number="APT-3"
    )
    cancelled = run(
        "online_booking.booking.cancel",
        {"number": "APT-3", "reason": "Fully booked that day"},
    )
    assert (
        cancelled.status,
        cancelled.cancellation_reason,
        cancelled.cancelled_by_customer,
    ) == (
        "cancelled",
        "Fully booked that day",
        False,
    )
    assert other.pk and third.pk


def test_deleting_is_the_owners_and_archives_the_appointment(pending):
    with pytest.raises(PermissionDenied):
        run("online_booking.booking.delete", {"number": "APT-1"}, role="hub_manager")
    answer = run("online_booking.booking.delete", {"number": "APT-1"}, role="hub_owner")
    assert (answer.id, answer.deleted) == (pending.id, True)
    pending.refresh_from_db()
    assert pending.deleted_at is not None
    with pytest.raises(NotFound):
        run("online_booking.booking.get", {"number": "APT-1"})


def test_an_appointment_that_is_not_online_is_not_the_inboxs(salon):
    make_appointment(
        salon.lucia,
        salon.ana,
        [salon.cut],
        at(TUESDAY, "10:00"),
        number="APT-C",
        source="counter",
    )
    with pytest.raises(NotFound) as error:
        run("online_booking.booking.cancel", {"number": "APT-C"})
    assert error.value.code == "online_booking.booking_not_found"
    assert Appointment.objects.get(number="APT-C").status == "confirmed"
