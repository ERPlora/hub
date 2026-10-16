"""Kitchen with the real Sales (a ``requires``): a ticket is a round of a check; what the till does to the
check reaches the kitchen (KITCHEN-F05, F18, F19, F27 to F29), by Sales' own operations, never by hand.

Cases from the old module's tests: tickets.hub (each send a round, numbered), rush_after_fire.hub (rush
after the fact), closed_check.hub and closed_check_leaves_the_display (charging serves the ready rounds and
what goes to paper, never what cooks), voided_or_merged_check.hub (a deleted check cancels, a merged one
hands its rounds), line_voided.hub and voided_line (a voided dish is struck with its reason; the round
follows what is left), merged_check_hands_its_rounds (the rounds of the absorbed check charge with the one
that stays).
"""

import pytest

from apps.kitchen.models import Ticket

from .conftest import (
    add_line,
    charge,
    ctx_for,
    fire,
    make_station,
    open_check,
    route_product,
    run,
)

pytestmark = pytest.mark.django_db


def board():
    return run("kitchen.ticket.board", {})


def send(order_id, **more):
    return run(
        "kitchen.ticket.send",
        {"order_id": str(order_id), **more},
        ctx_for(actor="luis"),
    )


def test_order_and_pay_at_the_bar_the_round_cooks_after_the_charge(clock, product):
    # «Pide y paga»: the round sent with the charge is cooked; the pass serves it.
    order = open_check("Bar 2")
    add_line(order.id, product("Burger"))
    ticket = send(order.id)
    charge(order.id, key="order-and-pay")
    clock.advance(minutes=4)
    assert [t.id for t in board().cooking] == [ticket.id]
    run("kitchen.ticket.ready", {"ticket_id": str(ticket.id)})
    assert [t.id for t in board().ready] == [ticket.id]
    run("kitchen.ticket.serve", {"ticket_id": str(ticket.id)})
    assert board().ready == []


def test_a_drink_round_to_a_paper_bar_leaves_once_the_check_is_charged(clock, product):
    bar = make_station("Bar", destination="printer", printer_usage="bar")
    beer = product("Beer")
    route_product(beer.id, bar)
    order = open_check("Table 4")
    add_line(order.id, beer)
    send(order.id)
    assert len(board().cooking) == 1
    charge(order.id, key="paper-bar")
    assert board().cooking == []


def test_the_rounds_of_a_check_as_the_till_sees_them(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    send(order.id, priority="rush")
    clock.advance(minutes=5)
    add_line(order.id, product("Cake"))
    fired = fire(order.id)
    run(
        "sale.order.void_line",
        {
            "order_id": str(order.id),
            "line_id": str(fired.order.lines[1].id),
            "reason": "Cold",
        },
    )
    tickets = run("kitchen.ticket.by_order", {"order_id": str(order.id)}).tickets
    assert [(t.round_no, t.priority, t.status) for t in tickets] == [
        (2, "normal", "cancelled"),
        (1, "rush", "pending"),
    ]
    assert [(i.name, i.status, i.void_reason) for i in tickets[0].items] == [
        ("Cake", "voided", "Cold")
    ]


def test_rushing_from_the_till_jumps_the_round_to_the_front(clock, product):
    first = open_check("Table 1")
    add_line(first.id, product("Soup"))
    send(first.id)
    clock.advance(minutes=1)
    second = open_check("Table 2")
    add_line(second.id, product("Salad"))
    later = send(second.id)
    run(
        "kitchen.ticket.set_rush", {"ticket_id": str(later.id)}, ctx_for("hub_employee")
    )
    assert [t.label for t in board().cooking] == ["Table 2", "Table 1"]


def test_merged_rounds_charge_with_the_check_that_stays(clock, product):
    first = open_check("Table 5")
    add_line(first.id, product("Burger"))
    absorbed = send(first.id)
    second = open_check("Table 6")
    add_line(second.id, product("Soup"))
    send(second.id)
    run(
        "sale.order.merge",
        {"from_order_id": str(first.id), "to_order_id": str(second.id)},
    )
    run("kitchen.ticket.ready", {"ticket_id": str(absorbed.id)})
    clock.advance(minutes=1)
    charge(second.id, key="merged")
    run("kitchen.ticket.sync", {}, ctx_for(permissions={"*"}))
    statuses = {ticket.label: ticket.status for ticket in Ticket.objects.all()}
    assert statuses == {"Table 5": "served", "Table 6": "pending"}


def test_a_split_check_closes_a_round_only_when_every_check_of_it_is_charged(
    clock, product
):
    order = open_check("Table 8")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = send(order.id)
    run("kitchen.ticket.ready", {"ticket_id": str(ticket.id)})
    split = run(
        "sale.order.split",
        {"order_id": str(order.id), "line_ids": [str(ticket.items[1].id)]},
    )
    clock.advance(minutes=1)
    charge(order.id, key="split-first")
    assert [t.id for t in board().ready] == [ticket.id]
    charge(split.new_order.id, key="split-second")
    assert board().ready == []


def test_a_round_fired_by_sales_alone_still_reaches_the_kitchen_and_is_numbered_in_order(
    clock, product
):
    for label in ("Table 1", "Table 2"):
        order = open_check(label)
        add_line(order.id, product(f"Dish of {label}"))
        fire(order.id)
        clock.advance(seconds=30)
    order = open_check("Table 3")
    add_line(order.id, product("Soup"))
    sent = send(order.id)
    assert sent.number == "20261014-0003"
    assert [t.number for t in board().cooking] == [
        "20261014-0001",
        "20261014-0002",
        "20261014-0003",
    ]
