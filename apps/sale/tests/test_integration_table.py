"""Sale with the real Tables app, by name only (SALE-F19; TABLE-F12, F13, F21): the till never imports
Tables — it seats the check on screen with ``table.session.open`` (its ``order_id``), reads its table
with ``table.session.by_order`` and takes it off with ``table.session.park``, as the till's «Choose
table» does. Tables, in turn, voids an empty check with the waiter's own session.
"""

import pytest
from live.context import system_context
from live.errors import PermissionDenied

from apps.sale.models import Order
from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture
def terrace(db):
    """Zone «Terrace» with tables 4 and 5, set up through Tables' own operations."""
    run("table.zone.create", {"name": "Terrace"}, system_context(A))
    for number in ("4", "5"):
        run("table.table.create", {"zone": "Terrace", "number": number}, system_context(A))


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def test_the_check_on_screen_is_seated_by_name_and_read_back_by_its_order(terrace, coffee):
    waiter = ctx_for(EMPLOYEE, actor="waiter")
    check = run("sale.order.open", {"lines": [{"product": "COF"}]}, waiter)
    seated = run(
        "table.session.open", {"table": "4", "zone": "Terrace", "order_id": str(check.id)}, waiter
    )
    assert (seated.order_id, seated.table_number, seated.status) == (check.id, "4", "open")
    # Tables retitles the check with its table, in the waiter's language.
    assert run("sale.order.get", {"order_id": str(check.id)}, waiter).label == "Table 4"
    (row,) = run("table.session.by_order", {"order_id": str(check.id)}, waiter).rows
    assert (row.id, row.table_number, row.zone_name, row.status) == (seated.id, "4", "Terrace", "open")


def test_taking_the_check_off_its_table_frees_the_table_and_keeps_the_check(terrace, coffee):
    waiter = ctx_for(EMPLOYEE)
    check = run("sale.order.open", {"lines": [{"product": "COF"}]}, waiter)
    seated = run("table.session.open", {"table": "4", "order_id": str(check.id)}, waiter)
    parked = run("table.session.park", {"id": str(seated.id)}, waiter)
    assert (parked.status, parked.table_id) == ("parked", None)
    assert run("table.table.get", {"table": "4"}, waiter).status == "available"
    assert Order.objects.get(pk=check.id).status == "open"
    # The till shows no table for it: by_order has no open seat left.
    rows = run("table.session.by_order", {"order_id": str(check.id)}, waiter).rows
    assert [(row.status, row.table_id) for row in rows] == [("parked", None)]


def test_a_waiter_closes_a_table_whose_check_is_empty_and_its_check_is_voided(terrace):
    waiter = ctx_for(EMPLOYEE)
    seated = run("table.session.open", {"table": "5"}, waiter)
    closed = run("table.session.close", {"id": str(seated.id)}, waiter)
    assert closed.status == "closed"
    assert Order.objects.get(pk=seated.order_id).status == "voided"


def test_a_waiter_cannot_void_through_tables_a_check_with_something_ordered(terrace, coffee):
    waiter = ctx_for(EMPLOYEE)
    seated = run("table.session.open", {"table": "5"}, waiter)
    run("sale.order.add_line", {"order_id": str(seated.order_id), "product": "COF"}, waiter)
    with pytest.raises(PermissionDenied):
        run("sale.order.void", {"order_id": str(seated.order_id)}, waiter)
    assert Order.objects.get(pk=seated.order_id).status == "open"
