"""What the floor paints of each table's bill (TABLE-F33): an occupied table carries what is left to charge on all its
open checks of Sales, the same figure Open checks shows; a table nobody sits at carries none. The plan reads it with
the checks it already reads, so a room with more occupied tables costs no more queries."""

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext

from base.tenancy.context import current_alias

from .conftest import (
    HUB_DB,
    add_line,
    charge,
    make_hold,
    make_session,
    make_table,
    open_check,
    run,
)

pytestmark = HUB_DB


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def cake(product):
    return product("Cake", "CAK", 420, "restaurant.food")


def seat(number: str):
    """A table ``number`` with a check of Sales open at it."""
    return make_session(make_table(number), order_id=open_check(f"Table {number}").id)


def amount(table_id) -> int | None:
    """The bill the plan paints on the table, as the list and the single read both say it."""
    single = run("table.table.get", {"id": str(table_id)}).amount
    [listed] = [row for row in run("table.table.list", {"limit": 100}).rows if row.id == table_id]
    assert listed.amount == single
    return single


def test_an_occupied_table_carries_what_its_check_has_run_up(coffee, cake):
    session = seat("4")
    add_line(session.order_id, coffee, quantity="2")
    add_line(session.order_id, cake)
    assert amount(session.table_id) == 2 * 150 + 420


def test_a_table_just_seated_carries_zero_until_something_is_ordered():
    session = seat("4")
    assert amount(session.table_id) == 0


def test_tables_nobody_sits_at_carry_no_bill():
    free = make_table("1")
    blocked = make_table("2", blocked=True)
    reserved = make_table("3")
    make_hold(reserved, starts_in=10)
    assert [run("table.table.get", {"id": str(t.id)}).status for t in (free, blocked, reserved)] == [
        "available",
        "blocked",
        "reserved",
    ]
    assert [amount(t.id) for t in (free, blocked, reserved)] == [None, None, None]


def test_a_split_table_carries_the_sum_of_all_its_checks(coffee, cake):
    first = seat("4")
    second = make_session(first.table, order_id=open_check("Table 4 (2)").id)
    third = make_session(first.table, order_id=open_check("Table 4 (3)").id)
    add_line(first.order_id, coffee)
    add_line(second.order_id, cake)
    add_line(third.order_id, coffee, quantity="3")
    assert amount(first.table_id) == 150 + 420 + 3 * 150


def test_after_charging_part_of_the_check_it_carries_what_is_left(coffee, cake):
    session = seat("4")
    paid = add_line(session.order_id, coffee).lines[-1].id
    add_line(session.order_id, cake)
    charge(session.order_id, key="floor-amount-part", line_ids=[paid])
    assert amount(session.table_id) == 420


def test_removing_a_line_takes_it_off_the_bill(coffee, cake):
    session = seat("4")
    add_line(session.order_id, coffee)
    gone = add_line(session.order_id, cake).lines[-1].id
    run("sale.order.remove_line", {"order_id": str(session.order_id), "line_id": str(gone)})
    assert amount(session.table_id) == 150


def floor_queries() -> int:
    with CaptureQueriesContext(connections[current_alias()]) as captured:
        run("table.table.list", {"limit": 100})
    return len(captured)


def test_the_bills_are_read_with_the_checks_not_one_query_per_table(coffee):
    add_line(seat("1").order_id, coffee)
    one = floor_queries()
    for number in ("2", "3", "4"):
        add_line(seat(number).order_id, coffee)
    assert floor_queries() == one
