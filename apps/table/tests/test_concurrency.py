"""Two devices at once (TABLE-F10, F15, F16): real sessions in threads, real row locks.

Two waiters seating the same table at the same instant leave one check (the old module let both in:
TABLES-F10 «sin ejecutar»); two transfers to the same free table, one; two crossed merges never deadlock.

A detail (a zone, a table, a check) that a deletion lands in the middle of answers what it read or 404,
never a 500.
"""

import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.db import connection, transaction
from django.test import RequestFactory
from django.utils import timezone
from live.errors import OperationError

from apps.sale.models import Order
from apps.table.models import Table, TableSession, Zone

from .conftest import ctx_for, make_session, make_table, make_zone, open_check, run

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


# ── The details: a deletion that lands in the middle of a read ─────────────────────────────────────

#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: The business's «Delete» of each kind of row: the row stays, marked deleted.
BUSINESS_DELETE = {
    Zone: "table.zone.delete",
    Table: "table.table.delete",
    TableSession: "table.session.delete",
}
#: Each detail, the row of the room it shows, how a person names it and how it says it is not found. Both
#: deletions take the row away from it: the business's «Delete» (``operation``) and the Hub admin's
#: (``row``: the row goes). A check is named by its table only while it is open, and neither deletion takes
#: an open check away (the business's refuses it, the admin's is protected by its trail): by its id only.
DETAILS = {
    "table.zone.get": ("patio", {"zone": "Patio"}, "table.zone_not_found"),
    "table.table.get": ("seven", {"table": "7"}, "table.table_not_found"),
    "table.session.get": ("closed", None, "table.session_not_found"),
}
DETAIL_CASES = [(detail, how) for detail in DETAILS for how in ("operation", "row")]
NAMED_CASES = [(detail, how) for detail, how in DETAIL_CASES if DETAILS[detail][1]]


@pytest.fixture
def room():
    # Named by nothing, so the Hub admin may delete each (PROTECT keeps a zone with tables, a table with
    # checks or holds, a check with its trail). The closed check has no trail: the staff empty it in its
    # inline before deleting the check.
    return SimpleNamespace(
        patio=make_zone("Patio"),
        seven=make_table("7"),
        closed=make_session(
            make_table("2"), status=TableSession.Status.CLOSED, closed_at=timezone.now()
        ),
    )


def admin_delete(target) -> None:
    """The Hub admin's «Delete» of ``target`` (its page), as the staff run it."""
    model_admin = admin.site._registry[type(target)]
    request = RequestFactory().post("/admin/")
    model_admin.delete_model(request, type(target).objects.get(pk=target.pk))


def delete(target, how: str) -> None:
    """Deletes ``target`` in this session, giving up after LOCK_TIMEOUT on a row another session holds (SET
    LOCAL: a session-level timeout would go back with the connection and reach the tests after this one)."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        if how == "row":
            admin_delete(target)
        else:
            run(BUSINESS_DELETE[type(target)], {"id": str(target.pk)})


@contextmanager
def deleted_after_the_first_read_of(target, how: str):
    """Commits the deletion of ``target`` (``how``) in another session right after the first statement of
    this one that reads its table: a deletion landing in the middle of a read, every time."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(target, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def attempt(call):
    """What ``call`` answers: its result, or the error it is refused with (a 500 is raised as it comes)."""
    try:
        return call()
    except OperationError as error:
        return error


@pytest.mark.parametrize(("detail", "how"), DETAIL_CASES)
def test_a_row_deleted_while_its_detail_is_read_is_never_a_server_error(room, detail, how):
    # The detail found the row and then read it again by its id: a deletion committed between the two
    # raised DoesNotExist (a 500). In one read it is the row as it was read.
    attribute, _, missing = DETAILS[detail]
    row = getattr(room, attribute)
    with deleted_after_the_first_read_of(row, how) as deletions:
        shown = run(detail, {"id": str(row.pk)})
    assert deleted(deletions) == ["ok"]
    assert shown.id == row.pk
    # What the deletion's event runs next: not found, and the open sheet closes.
    gone = attempt(lambda: run(detail, {"id": str(row.pk)}))
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, missing)


@pytest.mark.parametrize(("detail", "how"), NAMED_CASES)
def test_a_row_deleted_between_its_name_and_its_detail_is_not_found(room, detail, how):
    attribute, said, missing = DETAILS[detail]
    row = getattr(room, attribute)
    with deleted_after_the_first_read_of(row, how) as deletions:
        outcome = attempt(lambda: run(detail, said))
    assert deleted(deletions) == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, missing)
