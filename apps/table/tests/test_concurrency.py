"""Two devices at once (TABLE-F10, F15, F16): real sessions in threads, real row locks.

Two waiters seating the same table at the same instant leave one check (the old module let both in:
TABLES-F10 «sin ejecutar»); two transfers to the same free table, one; two crossed merges never deadlock.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError

from apps.sale.models import Order
from apps.table.models import TableSession

from .conftest import ctx_for, make_table, make_zone, open_check, run

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
    """The domain code of each refusal, the class of any other failure (an IntegrityError is a bug), «ok»."""
    return sorted(
        (getattr(result, "code", type(result).__name__) if isinstance(result, Exception) else "ok") for result in results
    )


def as_waiter(name: str, data: dict):
    return lambda: run(name, data, ctx_for(EMPLOYEE))


def test_two_waiters_seating_the_same_table_at_once_leave_one_check():
    table = make_table("4", zone=make_zone())
    results = at_once(
        *(
            as_waiter("table.session.open", {"table_id": str(table.id)})
            for _ in range(4)
        )
    )
    assert codes(results) == [
        "ok",
        "table.table_not_available",
        "table.table_not_available",
        "table.table_not_available",
    ]
    assert TableSession.objects.filter(table=table, status="open").count() == 1
    # The losers never opened a check in Sales: the table was locked before anything was written.
    assert Order.objects.count() == 1


def test_two_transfers_to_the_same_free_table_leave_one_there():
    zone = make_zone()
    one, two, free = (
        make_table("1", zone=zone),
        make_table("2", zone=zone),
        make_table("3", zone=zone),
    )
    first = run("table.session.open", {"table_id": str(one.id)})
    second = run("table.session.open", {"table_id": str(two.id)})
    results = at_once(
        as_waiter(
            "table.session.transfer", {"id": str(first.id), "to_table_id": str(free.id)}
        ),
        as_waiter(
            "table.session.transfer",
            {"id": str(second.id), "to_table_id": str(free.id)},
        ),
    )
    assert codes(results) == ["ok", "table.table_not_available"]
    assert TableSession.objects.filter(table=free, status="open").count() == 1


def test_two_crossed_merges_never_deadlock_and_the_first_wins():
    zone = make_zone()
    one, two = make_table("1", zone=zone), make_table("2", zone=zone)
    first = run("table.session.open", {"table_id": str(one.id)})
    second = run("table.session.open", {"table_id": str(two.id)})
    results = at_once(
        as_waiter(
            "table.session.merge",
            {"id": str(first.id), "into_session_id": str(second.id)},
        ),
        as_waiter(
            "table.session.merge",
            {"id": str(second.id), "into_session_id": str(first.id)},
        ),
    )
    assert codes(results)[0] == "ok"
    assert codes(results)[1] in {"table.session_not_active", "table.nothing_to_merge"}
    assert TableSession.objects.filter(status="open").count() == 1
    assert TableSession.objects.filter(status="merged").count() == 1


def test_two_seats_bringing_the_same_check_of_sales_leave_it_at_one_table():
    # The check of Sales is locked before asking who holds it: the second waits and is told where it is.
    zone = make_zone()
    one, two = make_table("1", zone=zone), make_table("2", zone=zone)
    order = open_check("Ana — bar")
    results = at_once(
        as_waiter("table.session.open", {"table_id": str(one.id), "order_id": str(order.id)}),
        as_waiter("table.session.open", {"table_id": str(two.id), "order_id": str(order.id)}),
    )
    assert codes(results) == ["ok", "table.order_elsewhere"]
    assert TableSession.objects.filter(order_id=order.id, status="open").count() == 1


def test_two_zones_with_the_same_name_at_once_leave_one_and_a_409():
    results = at_once(*(lambda: run("table.zone.create", {"name": "Terrace"}) for _ in range(2)))
    assert codes(results) == ["ok", "table.zone_name_taken"]


def test_two_first_saves_of_the_settings_at_once_both_land_in_one_row():
    from apps.table.models import TableSettings

    results = at_once(
        lambda: run("table.settings.update", {"timer_warning_minutes": 30}),
        lambda: run("table.settings.update", {"prompt_guests_on_seat": False}),
    )
    assert codes(results) == ["ok", "ok"]
    settings = TableSettings.objects.get()
    assert (settings.timer_warning_minutes, settings.prompt_guests_on_seat) == (30, False)
