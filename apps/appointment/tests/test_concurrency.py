"""Two bookings of the same professional at once: real sessions in threads, real row locks (WORKBOOK «Para
quien lo mantiene»: solapes con bloqueo).

Whichever comes first wins; the other one waits for the staff record's lock, then sees the first booking
and is refused with the real reason. Two bookings on the same day never share a number, and two runs of
the same series never book a date twice.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.appointment.models import Appointment
from apps.staff.models import Member
from apps.staff.tests.conftest import deleted_on_screen

from .conftest import MONDAY, make_settings, run, wall

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("anytime"),
]


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list[str]:
    return sorted(getattr(result, "code", "ok") for result in results)


def booking(salon, start: str, staff=None):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str((staff or salon.ana).id),
        "start": wall(MONDAY, start),
    }
    return lambda: run("appointment.appointment.create", data)


def test_two_bookings_of_the_same_time_with_overlaps_off_one_wins(salon):
    make_settings(allow_overlapping=False)
    assert codes(at_once(booking(salon, "10:00"), booking(salon, "10:15"))) == [
        "appointment.slot_taken",
        "ok",
    ]
    assert Appointment.objects.count() == 1


def test_two_bookings_of_the_same_time_at_the_front_desk_the_second_is_asked_to_confirm(
    salon,
):
    results = at_once(booking(salon, "10:00"), booking(salon, "10:00"))
    assert codes(results) == ["appointment.overlap_needs_confirmation", "ok"]


def test_two_professionals_at_the_same_time_both_book_with_their_own_numbers(salon):
    make_settings(allow_overlapping=False)
    results = at_once(booking(salon, "10:00"), booking(salon, "10:00", staff=salon.bea))
    assert codes(results) == ["ok", "ok"]
    assert len({result.number for result in results}) == 2


def test_two_runs_of_the_same_series_never_book_a_date_twice(salon):
    out = run(
        "appointment.recurring.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "frequency": "weekly",
            "start_date": MONDAY.isoformat(),
            "time": "10:00",
            "max_occurrences": 2,
        },
    )
    Appointment.objects.filter(recurring_id=out.recurring.id).delete()
    again = lambda: run(
        "appointment.recurring.materialize", {"id": str(out.recurring.id)}
    )  # noqa: E731
    at_once(again, again)
    dates = list(
        Appointment.objects.filter(recurring_id=out.recurring.id).values_list(
            "occurrence_date", flat=True
        )
    )
    assert len(dates) == len(set(dates)) == 2


def test_two_charges_of_the_same_appointment_at_once_open_one_check(salon):
    from apps.sale.models import Order

    booked = booking(salon, "10:00")()
    charge = lambda: run("appointment.appointment.charge", {"id": str(booked.id)})  # noqa: E731
    results = at_once(charge, charge)
    assert codes(results) == ["ok", "ok"]
    assert results[0].order_id == results[1].order_id
    assert Order.objects.filter(appointment_id=booked.id).count() == 1


# ── The Hub admin's «Delete» of a professional while a booking is written ─────────────────────────
#
# A booking holds the professional's record and then writes the appointment, which protects the record.
# Django's delete page and its «Delete selected» check what protects a record before deleting it: the check
# ran before the booking committed, and the deletion then found the appointment (a 500). The admin locks the
# record before the check, so it waits for the booking and answers «Cannot delete», as for one protected
# before.


@pytest.mark.parametrize("how", ["page", "list"])
def test_a_booking_while_the_hub_admin_deletes_the_professional_leaves_them_protected(salon, how):
    books = lambda sql: sql.lstrip().startswith('INSERT INTO "appointment_appointment"')  # noqa: E731
    with deleted_on_screen(salon.ana, how, books) as answers:
        booking(salon, "10:00")()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Cannot delete staff member")
    assert len(answer.context["protected"]) == 1
    assert Member.objects.filter(pk=salon.ana.pk).exists()
    assert Appointment.objects.filter(staff=salon.ana).count() == 1
