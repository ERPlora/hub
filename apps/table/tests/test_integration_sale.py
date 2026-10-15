"""Tables with the real Sales and Customers apps, end to end (no mocks): what a waiter does at the
tables and what the till does with their checks.

Cases from the old module's session_history.hub (charging the order in full frees the table, a partial
charge leaves it occupied, voiding a partial charge keeps the party seated, closing by hand refuses a table
whose bill is still open) and session_paid_total (what each check charged).
"""

import pytest
from live.context import system_context

from apps.table import events

from .conftest import (
    A,
    add_line,
    charge,
    ctx_for,
    make_customer,
    make_table,
    make_zone,
    run,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def table():
    return make_table("4", zone=make_zone("Terrace"))


def seat(table, **more):
    return run(
        "table.session.open", {"table_id": str(table.id), **more}, ctx_for(EMPLOYEE)
    )


def floor(table):
    return run("table.table.get", {"id": str(table.id)})


def open_checks():
    return run(
        "sale.order.list", {"status": "open", "limit": 100}, ctx_for(EMPLOYEE)
    ).rows


def test_seating_leaves_an_open_check_titled_with_the_table_among_the_tills_open_checks(
    table,
):
    session = seat(table, guests_count=2)
    assert [(row.id, row.label) for row in open_checks()] == [
        (session.order_id, "Table 4")
    ]


def test_charging_the_check_in_full_frees_the_table(table, coffee):
    session = seat(table)
    add_line(session.order_id, coffee, ctx=ctx_for(EMPLOYEE))
    add_line(session.order_id, coffee, ctx=ctx_for(EMPLOYEE))
    charge(session.order_id, key="full-1", ctx=ctx_for(EMPLOYEE))
    assert floor(table).status == "available"
    row = run("table.session.get", {"id": str(session.id)})
    assert (row.status, row.paid_total) == ("closed", 300)
    # When the relay delivers Sales' event, the stored check closes too (and it is idempotent).
    events.react(A, "sale.order.completed", {"order_id": str(session.order_id)})
    assert run("table.session.list", {"status": "open"}).total == 0


def test_a_partial_charge_leaves_the_table_occupied_and_voiding_it_keeps_the_party_seated(
    table, coffee
):
    session = seat(table)
    first = add_line(session.order_id, coffee).lines[0]
    add_line(session.order_id, coffee)
    sale = charge(session.order_id, key="part-1", line_ids=[first.id])
    assert floor(table).status == "occupied"
    assert run("table.session.get", {"id": str(session.id)}).paid_total == 150
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong card"})
    assert floor(table).status == "occupied"
    assert run("table.session.get", {"id": str(session.id)}).paid_total is None


def test_closing_by_hand_refuses_a_table_whose_bill_is_still_open(table, coffee):
    session = seat(table)
    add_line(session.order_id, coffee)
    from live.errors import Conflict

    with pytest.raises(Conflict) as refused:
        run("table.session.close", {"id": str(session.id)}, ctx_for(EMPLOYEE))
    assert refused.value.code == "table.session_bill_open"


def test_voiding_the_tables_check_in_sales_frees_the_table(table, coffee):
    session = seat(table)
    add_line(session.order_id, coffee)
    run("sale.order.void", {"order_id": str(session.order_id)}, ctx_for("hub_manager"))
    assert floor(table).status == "available"
    assert run("table.session.get", {"id": str(session.id)}).status == "closed"


def test_a_split_table_charges_each_check_on_its_own(table, coffee):
    session = seat(table, guests_count=2)
    mine = add_line(session.order_id, coffee).lines[0]
    add_line(session.order_id, coffee)
    split = run(
        "table.session.split",
        {"id": str(session.id), "line_ids": [str(mine.id)]},
        ctx_for(EMPLOYEE),
    )
    charge(split.new_session.order_id, key="split-1")
    row = floor(table)
    assert (row.status, [check.id for check in row.checks]) == (
        "occupied",
        [session.id],
    )
    charge(session.order_id, key="split-2")
    assert floor(table).status == "available"


def test_a_transferred_check_is_charged_at_its_new_table(table, coffee):
    target = make_table("9", zone=table.zone)
    session = seat(table)
    add_line(session.order_id, coffee)
    moved = run(
        "table.session.transfer",
        {"id": str(session.id), "to_table": "9"},
        ctx_for(EMPLOYEE),
    )
    assert [row.label for row in open_checks()] == ["Table 9"]
    charge(moved.order_id, key="moved-1")
    assert (floor(table).status, floor(target).status) == ("available", "available")
    assert run("table.session.get", {"id": str(moved.id)}).paid_total == 150


def test_merged_tables_pay_one_check_with_every_line(table, coffee):
    other = make_table("5", zone=table.zone)
    source = seat(table)
    staying = seat(other)
    add_line(source.order_id, coffee)
    add_line(staying.order_id, coffee)
    run(
        "table.session.merge",
        {"id": str(source.id), "into_table_id": str(other.id)},
        ctx_for(EMPLOYEE),
    )
    assert [(row.label, row.lines_count) for row in open_checks()] == [("Table 5", 2)]
    charge(staying.order_id, key="merged-1")
    assert run("table.session.get", {"id": str(staying.id)}).paid_total == 300


def test_the_customer_of_a_table_is_the_one_the_till_gets_back(table):
    ana = make_customer("Ana García", phone="+34600111222")
    session = seat(table, customer="+34 600 111 222")
    linked = run(
        "customer.order.customer",
        {"order_id": str(session.order_id)},
        system_context(A),
    )
    assert linked.customer_id == ana.id
    assert floor(table).checks[0].customer_name == "Ana García"
