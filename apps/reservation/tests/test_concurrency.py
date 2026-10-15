"""Two hosts at once (RESERVATION-F06, F16): real sessions in threads, real row locks.

Two reservations for the same table and time leave one (the old module did not check it); the last place
of a slot goes to one reservation (the old gate's promise), also when a conversion from the waitlist races
a new booking. The losers get their reason and write nothing.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.customer.models import Customer
from apps.reservation.models import Reservation

from .conftest import (
    THURSDAY,
    book,
    ctx_for,
    make_entry,
    make_slot,
    make_table,
    open_week,
    run,
    set_rules,
)

pytestmark = pytest.mark.django_db(transaction=True)

EMPLOYEE = "hub_employee"


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
        except (
            Exception
        ) as error:  # an unexpected failure (a deadlock…) is reported by the test
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


def codes(results) -> list:
    return sorted(getattr(result, "code", "ok") for result in results)


@pytest.fixture(autouse=True)
def saved_rules(db):
    """The book's settings row exists before the race: creating it would serialize the writers by itself
    (its unique index), and hide whether the lock does."""
    set_rules()


def as_host(**data):
    return lambda: book(ctx=ctx_for(EMPLOYEE), **data)


def test_two_reservations_for_the_same_table_and_time_leave_one():
    open_week()
    table = make_table("5")
    results = at_once(
        *(
            as_host(
                table_id=str(table.id),
                guest_name=f"Guest {n}",
                guest_phone=f"60011122{n}",
            )
            for n in range(4)
        )
    )
    assert codes(results) == [
        "ok",
        "reservation.table_taken",
        "reservation.table_taken",
        "reservation.table_taken",
    ]
    assert Reservation.objects.filter(table=table).count() == 1
    # The losers left no card behind either: their whole transaction rolled back.
    assert Customer.objects.count() == 1


def test_the_last_place_of_a_slot_goes_to_one_reservation():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    results = at_once(
        *(
            as_host(guest_name=f"Guest {n}", guest_phone=f"60011122{n}")
            for n in range(3)
        )
    )
    assert codes(results) == [
        "ok",
        "reservation.no_capacity",
        "reservation.no_capacity",
    ]
    assert Reservation.objects.count() == 1


def test_a_conversion_and_a_new_booking_racing_for_the_last_place_leave_one():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    entry = make_entry()
    results = at_once(
        as_host(guest_name="Ana", guest_phone="600111222"),
        lambda: run(
            "reservation.waitlist.convert", {"id": str(entry.id)}, ctx_for(EMPLOYEE)
        ),
    )
    assert codes(results) == ["ok", "reservation.no_capacity"]
    assert Reservation.objects.count() == 1
