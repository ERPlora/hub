"""Two customers booking the same time at once: real sessions in threads, real row locks.

Citas locks the professional's staff record before judging the time, so two online bookings of the same
professional at the same time wait for each other: one enters, the other sees it and is refused. One mobile
booking twice at once waits on its card's lock, so its limit of upcoming bookings holds.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.appointment.models import Appointment

from .conftest import booking_data, make_page, public

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
