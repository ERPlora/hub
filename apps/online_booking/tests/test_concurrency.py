"""Two customers booking the same time at once: real sessions in threads, real row locks.

Citas locks the professional's staff record before judging the time, so two online bookings of the same
professional at the same time wait for each other: one enters, the other sees it and is refused. One mobile
booking twice at once waits on its card's lock, so its limit of upcoming bookings holds.

A booking's detail that a deletion lands in the middle of answers what it read or 404, never a 500.
"""

import threading
from contextlib import contextmanager

import pytest
from django.contrib import admin
from django.db import connection
from django.test import RequestFactory
from live.errors import OperationError

from apps.appointment.models import Appointment
from apps.online_booking.models import Booking

from .conftest import TUESDAY, at, booking_data, make_appointment, make_page, public, run

pytestmark = pytest.mark.django_db(transaction=True)


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
    return sorted(
        getattr(result, "code", "ok") if isinstance(result, Exception) else "ok"
        for result in results
    )


def book(salon, ip: str, phone: str, **fields):
    return lambda: public(
        "book", booking_data(salon, "10:00", phone=phone, **fields), ip=ip
    )


def test_two_customers_and_the_same_professional_at_the_same_time_one_wins(salon):
    ana = str(salon.ana.id)
    results = at_once(
        book(salon, "198.51.100.1", "612000001", staff_id=ana),
        book(salon, "198.51.100.2", "612000002", staff_id=ana),
    )
    assert codes(results) == ["appointment.slot_taken", "ok"]
    assert Appointment.objects.filter(staff=salon.ana).count() == 1


def test_with_anyone_and_one_professional_free_one_wins(salon):
    salon.bea.is_bookable = False
    salon.bea.save()
    results = at_once(
        book(salon, "198.51.100.1", "612000001"),
        book(salon, "198.51.100.2", "612000002"),
    )
    assert codes(results) == ["ok", "online_booking.time_taken"]
    assert Appointment.objects.count() == 1


def test_with_anyone_two_professionals_take_two_customers(salon):
    results = at_once(
        book(salon, "198.51.100.1", "612000001"),
        book(salon, "198.51.100.2", "612000002"),
    )
    assert codes(results) == ["ok", "ok"]
    assert sorted(Appointment.objects.values_list("staff_name", flat=True)) == [
        "Ana López",
        "Bea Ruiz",
    ]


def test_one_mobile_twice_at_once_keeps_its_limit(salon):
    make_page(max_upcoming_per_customer=1)
    results = at_once(
        book(salon, "198.51.100.1", "600111222", staff_id=str(salon.ana.id)),
        book(salon, "198.51.100.2", "600111222", staff_id=str(salon.bea.id)),
    )
    assert codes(results) == ["ok", "online_booking.too_many_upcoming"]


def test_a_new_mobile_twice_at_once_is_one_card_and_keeps_its_limit(salon):
    from apps.customer.models import Customer

    make_page(max_upcoming_per_customer=1)
    results = at_once(
        book(salon, "198.51.100.1", "699 555 444", staff_id=str(salon.ana.id)),
        book(salon, "198.51.100.2", "699 555 444", staff_id=str(salon.bea.id)),
    )
    assert codes(results) == ["ok", "online_booking.too_many_upcoming"]
    assert Customer.objects.filter(phone="+34699555444").count() == 1


def test_one_device_six_times_at_once_five_enter(salon):
    ana = str(salon.ana.id)
    calls = [
        (lambda hhmm=hhmm, n=n: public("book", booking_data(salon, hhmm, phone=f"61200000{n}", staff_id=ana), ip="198.51.100.9"))
        for n, hhmm in enumerate(("09:00", "09:30", "10:00", "10:30", "11:00", "11:30"))
    ]
    results = at_once(*calls)
    assert codes(results) == ["ok"] * 5 + ["online_booking.too_many_bookings"]
    assert Appointment.objects.count() == 5


# ── A deletion that lands in the middle of a booking's detail ────────────────────────────────────
#
# The detail found the booking and then loaded it again by its id: a deletion committed between the two reads
# raised DoesNotExist (a 500) when the Hub admin deleted it (the row goes). In one read it is the booking as it
# was read; what the deletion's event runs next says it is not found.

#: How a booking is taken away, and whether it still has its page link: the Hub admin's «Delete» from the
#: appointment's page or with the list's «Delete selected» (the row goes with its lines; only once no link
#: protects it), or the business's «Delete» in the inbox (the row is marked).
DELETIONS = {"delete_model": False, "delete_queryset": False, "operation": True}

#: How the detail is asked for: by id, by number, or as a person says it (the customer and the day, or her next).
REFS = {
    "id": lambda booked: {"id": str(booked.id)},
    "number": lambda booked: {"number": booked.number.lower()},
    "customer and day": lambda booked: {"customer": "Lucía", "date": TUESDAY.isoformat()},
    "customer's next": lambda booked: {"customer": "Lucía"},
}


def delete(appointment: Appointment, how: str) -> None:
    """Takes ``appointment`` away in this session, ``how`` it says (see ``DELETIONS``), as the staff run it."""
    if how == "operation":
        run("online_booking.booking.delete", {"id": str(appointment.pk)})
        return
    model_admin = admin.site._registry[Appointment]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, Appointment.objects.filter(pk=appointment.pk))
    else:
        model_admin.delete_model(request, Appointment.objects.get(pk=appointment.pk))


@contextmanager
def deleted_after_the_first_read_of(appointment: Appointment, how: str):
    """Commits the deletion of ``appointment`` in another session right after the first statement of this one
    that reads its table: a deletion landing in the middle of a read, every time. Yields its outcome."""
    table = f'FROM "{Appointment._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(appointment, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


@pytest.mark.parametrize("how", sorted(DELETIONS))
@pytest.mark.parametrize("ref", sorted(REFS))
def test_a_booking_deleted_while_its_detail_is_read_is_never_a_server_error(salon, ref, how):
    via_page = DELETIONS[how]
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(TUESDAY, "10:00"))
    if via_page:
        Booking.objects.create(appointment=booked, token_hash="a" * 64)
    with deleted_after_the_first_read_of(booked, how) as deletions:
        shown = run("online_booking.booking.get", REFS[ref](booked))
    assert deletions == [None]
    assert (shown.id, shown.number, shown.customer_name, shown.status, shown.via_page) == (
        booked.id,
        booked.number,
        "Lucía Pérez",
        "confirmed",
        via_page,
    )
    # What the deletion's event runs next: not found, and the open sheet closes.
    try:
        gone = run("online_booking.booking.get", REFS[ref](booked))
    except OperationError as error:
        gone = error
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, "online_booking.booking_not_found")
