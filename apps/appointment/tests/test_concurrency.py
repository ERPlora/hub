"""Two bookings of the same professional at once: real sessions in threads, real row locks (WORKBOOK «Para
quien lo mantiene»: solapes con bloqueo).

Whichever comes first wins; the other one waits for the staff record's lock, then sees the first booking
and is refused with the real reason. Two bookings on the same day never share a number, and two runs of
the same series never book a date twice.

A detail (an appointment, a series) that a deletion lands in the middle of answers what it read or 404,
never a 500.
"""

import threading
from contextlib import contextmanager

import pytest
from django.contrib import admin
from django.db import connection
from django.test import RequestFactory
from live.errors import OperationError

from apps.appointment.models import Appointment
from apps.staff.models import Member
from apps.staff.tests.conftest import deleted_on_screen

from .conftest import MONDAY, at, make_appointment, make_series, make_settings, run, wall

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


# ── A deletion that lands in the middle of a detail ─────────────────────────────────────────────
#
# The series' detail found it and then loaded it again by its id: a deletion committed between the two reads
# raised DoesNotExist (a 500) when the Hub admin deleted it (the row goes), and mixed both reads when the
# business deleted it (the row stays, marked: the detail showed it paused). In one read it is the series as
# it was read; what the deletion's event runs next says it is not found. An appointment's detail already
# reads its row once: it stays here so that a second read never comes back.

#: How a detail's row is taken away: the Hub admin's «Delete» from its page or with the list's «Delete
#: selected» (the row goes, with what its ``on_delete`` takes), or the business's «Delete» (the row is marked).
DELETIONS = ["delete_model", "delete_queryset", "operation"]

#: Each detail: how its row is made, the business's «Delete» of it, what the detail shows of it (and what it
#: was made with), and how it says it is not found.
DETAILS = {
    "appointment.recurring.get": (
        make_series,
        "appointment.recurring.delete",
        lambda shown: (shown.id, shown.customer_name, shown.frequency, shown.is_active),
        lambda series: (series.id, "Lucía Pérez", "weekly", True),
        "appointment.recurring_not_found",
    ),
    "appointment.appointment.get": (
        lambda salon: make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")
        ),
        "appointment.appointment.delete",
        lambda shown: (shown.id, shown.customer_name, shown.status),
        lambda appointment: (appointment.id, "Lucía Pérez", "confirmed"),
        "appointment.appointment_not_found",
    ),
}


def delete(target, how: str, business_delete: str) -> None:
    """Takes ``target`` away in this session, ``how`` it says (see ``DELETIONS``), as the staff run it."""
    if how == "operation":
        run(business_delete, {"id": str(target.pk)})
        return
    model_admin = admin.site._registry[type(target)]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, type(target).objects.filter(pk=target.pk))
    else:
        model_admin.delete_model(request, type(target).objects.get(pk=target.pk))


@contextmanager
def deleted_after_the_first_read_of(target, how: str, business_delete: str):
    """Commits the deletion of ``target`` in another session right after the first statement of this one that
    reads its table: a deletion landing in the middle of a read, every time. Yields its outcome."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(target, how, business_delete)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("detail", sorted(DETAILS))
def test_a_row_deleted_while_its_detail_is_read_is_never_a_server_error(salon, detail, how):
    make, business_delete, shows, made_with, missing = DETAILS[detail]
    target = make(salon)
    with deleted_after_the_first_read_of(target, how, business_delete) as deletions:
        shown = run(detail, {"id": str(target.pk)})
    assert [getattr(outcome, "code", "ok") for outcome in deletions] == ["ok"]
    assert shows(shown) == made_with(target)
    # What the deletion's event runs next: not found, and the open sheet closes.
    try:
        gone = run(detail, {"id": str(target.pk)})
    except OperationError as error:
        gone = error
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, missing)
