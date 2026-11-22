"""What the floor paints of each table's bill (TABLE-F33): an occupied table carries what is left to charge on all its
open checks of Sales, the same figure Open checks shows; a table nobody sits at carries none. And whether it has asked
for the bill (TABLE-F34): one of its open checks had its bill printed in Sales, until that check is charged in full or
deleted. And who serves it: who serves its check in Sales («Served by» of the till, SALE-F16), or who seated it while
nobody was chosen. The plan reads all of it with the checks it already reads, so a room with more occupied tables costs
no more queries."""

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext
from live.context import system_context

from base.tenancy.context import current_alias

from .conftest import (
    HUB_DB,
    A,
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


def bill_requested(table_id) -> bool:
    """Whether the plan says the table asked for the bill, as the list and the single read both say it."""
    single = run("table.table.get", {"id": str(table_id)}).bill_requested
    [listed] = [row for row in run("table.table.list", {"limit": 100}).rows if row.id == table_id]
    assert listed.bill_requested == single
    return single


def print_bill(order_id):
    run("sale.order.print_bill", {"order_id": str(order_id)})


def test_a_table_whose_bill_was_printed_has_asked_for_it(coffee):
    asked, other = seat("4"), seat("5")
    add_line(asked.order_id, coffee)
    add_line(other.order_id, coffee)
    print_bill(asked.order_id)
    assert (bill_requested(asked.table_id), bill_requested(other.table_id)) == (True, False)


def test_tables_nobody_sits_at_never_asked_for_the_bill():
    free = make_table("1")
    reserved = make_table("3")
    make_hold(reserved, starts_in=10)
    assert [bill_requested(t.id) for t in (free, reserved)] == [False, False]


def test_with_several_checks_one_printed_bill_is_enough(coffee):
    first = seat("4")
    second = make_session(first.table, order_id=open_check("Table 4 (2)").id)
    add_line(first.order_id, coffee)
    add_line(second.order_id, coffee)
    print_bill(second.order_id)
    assert bill_requested(first.table_id) is True


def test_it_stays_while_lines_come_and_part_is_paid_and_goes_once_paid_in_full(coffee, cake):
    session = seat("4")
    add_line(session.order_id, coffee)
    print_bill(session.order_id)
    paid = add_line(session.order_id, cake).lines[-1].id
    charge(session.order_id, key="floor-bill-part", line_ids=[paid])
    assert bill_requested(session.table_id) is True
    charge(session.order_id, key="floor-bill-rest")
    assert run("table.table.get", {"id": str(session.table_id)}).status == "available"
    assert bill_requested(session.table_id) is False


def test_a_check_closed_takes_its_mark_and_leaves_the_others_unmarked(coffee):
    first = seat("4")
    second = make_session(first.table, order_id=open_check("Table 4 (2)").id)
    third = make_session(first.table, order_id=open_check("Table 4 (3)").id)
    for session in (first, second, third):
        add_line(session.order_id, coffee)
    print_bill(first.order_id)
    print_bill(second.order_id)
    charge(first.order_id, key="floor-bill-first")
    run("sale.order.void", {"order_id": str(second.order_id)})
    assert run("table.table.get", {"id": str(first.table_id)}).status == "occupied"
    assert bill_requested(first.table_id) is False


def test_the_mark_goes_with_its_check_to_another_table(coffee):
    session = seat("4")
    target = make_table("9")
    add_line(session.order_id, coffee)
    print_bill(session.order_id)
    run("table.session.transfer", {"id": str(session.id), "to_table_id": str(target.id)})
    assert (bill_requested(session.table_id), bill_requested(target.id)) == (False, True)


def floor_queries() -> int:
    with CaptureQueriesContext(connections[current_alias()]) as captured:
        run("table.table.list", {"limit": 100})
    return len(captured)


def test_the_bills_are_read_with_the_checks_not_one_query_per_table(coffee):
    add_line(seat("1").order_id, coffee)
    one = floor_queries()
    for number in ("2", "3", "4"):
        order_id = seat(number).order_id
        add_line(order_id, coffee)
        print_bill(order_id)
    assert floor_queries() == one


def served_by(table_id) -> tuple[str, list[str]]:
    """Who the plan says serves the table and each of its checks, as the list and the single read both say it."""
    single = run("table.table.get", {"id": str(table_id)})
    [listed] = [row for row in run("table.table.list", {"limit": 100}).rows if row.id == table_id]
    said = (single.waiter_name, [check.waiter_name for check in single.checks])
    assert (listed.waiter_name, [check.waiter_name for check in listed.checks]) == said
    return said


def serve(order_id, staff_id):
    run("sale.order.set_staff", {"order_id": str(order_id), "staff_id": staff_id and str(staff_id)})


def test_a_table_is_served_by_who_serves_its_check_and_by_who_seated_it_while_nobody_is_chosen():
    session = make_session(make_table("6"), order_id=open_check("Table 6").id, waiter_name="Luis Pérez")
    assert served_by(session.table_id) == ("Luis Pérez", ["Luis Pérez"])
    lucia = run("staff.member.create", {"first_name": "Lucia", "last_name": "Garcia"}, system_context(A))
    serve(session.order_id, lucia.id)
    assert served_by(session.table_id) == ("Lucia Garcia", ["Lucia Garcia"])
    serve(session.order_id, None)
    assert served_by(session.table_id) == ("Luis Pérez", ["Luis Pérez"])


def test_who_serves_is_read_with_the_checks_not_one_query_per_table(coffee):
    seat("1")
    one = floor_queries()
    lucia = run("staff.member.create", {"first_name": "Lucia", "last_name": "Garcia"}, system_context(A))
    for number in ("2", "3"):
        serve(seat(number).order_id, lucia.id)
    assert floor_queries() == one
