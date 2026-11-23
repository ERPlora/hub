"""A round already sent says where its check is now (KITCHEN-F05, F10, F21): moving a check to another table
(TABLE-F15), merging it into another (TABLE-F16) or seating a parked one again (TABLE-F24) gives its tickets still on
the line the check's new title, read as Sales has it and saved by the next write of the kitchen. A ticket already
served or cancelled keeps the title it went out with.
"""

from live.context import system_context

from apps.kitchen.models import Ticket
from apps.table.tests.conftest import make_table, make_zone
from base.tenancy.context import use_hub

from .conftest import HUB_DB, A, B, add_line, ctx_for, open_check, run

pytestmark = HUB_DB

EMPLOYEE = "hub_employee"


def seat(table) -> object:
    return run("table.session.open", {"table_id": str(table.id)}, ctx_for(EMPLOYEE))


def sent(session, product, name: str = "Burger"):
    add_line(session.order_id, product(name))
    return run("kitchen.ticket.send", {"order_id": str(session.order_id)}, ctx_for(EMPLOYEE))


def labels(order_id) -> list[str]:
    return [t.label for t in run("kitchen.ticket.by_order", {"order_id": str(order_id)}).tickets]


def board_labels() -> list[str]:
    return sorted(t.label for t in run("kitchen.ticket.board", {}).cooking)


def save_everything():
    return run("kitchen.ticket.sync", {}, system_context(A))


def test_a_sent_round_says_the_table_its_check_was_moved_to(clock, product):
    four = make_table("4", zone=make_zone())
    make_table("9", zone=four.zone)
    session = seat(four)
    ticket = sent(session, product)
    assert ticket.label == "Table 4"

    moved = run("table.session.transfer", {"id": str(session.id), "to_table": "9"}, ctx_for(EMPLOYEE))

    assert labels(moved.order_id) == ["Table 9"]
    assert board_labels() == ["Table 9"]
    found = run("kitchen.ticket.get", {"ticket": "table 9"}, ctx_for(EMPLOYEE))
    assert found.id == ticket.id


def test_the_rounds_of_a_merged_check_say_the_table_that_stays(clock, product):
    nine, ten = make_table("9"), make_table("10")
    staying, absorbed = seat(nine), seat(ten)
    sent(staying, product, "Soup")
    sent(absorbed, product, "Burger")

    run("table.session.merge", {"id": str(absorbed.id), "into_table_id": str(nine.id)}, ctx_for(EMPLOYEE))

    assert labels(staying.order_id) == ["Table 9", "Table 9"]
    assert board_labels() == ["Table 9", "Table 9"]


def test_a_parked_check_seated_again_gives_its_rounds_the_new_table(clock, product):
    ten, three = make_table("10"), make_table("3")
    session = seat(ten)
    sent(session, product)
    parked = run("table.session.park", {"id": str(session.id)}, ctx_for(EMPLOYEE))
    assert labels(session.order_id) == ["Table 10"]

    run("table.session.restore", {"id": str(parked.id), "table_id": str(three.id)}, ctx_for(EMPLOYEE))

    assert labels(session.order_id) == ["Table 3"]
    answer = run("kitchen.ticket.get", {"ticket": "table 3"}, ctx_for(EMPLOYEE))
    assert answer.label == "Table 3"


def test_the_next_write_saves_the_new_title_and_a_served_round_keeps_it(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    run("sale.order.set_label", {"order_id": str(order.id), "label": "Table 9"})
    assert Ticket.objects.get(pk=ticket.id).label == "Table 4"

    save_everything()

    assert Ticket.objects.get(pk=ticket.id).label == "Table 9"
    run("kitchen.ticket.ready", {"ticket_id": str(ticket.id)})
    run("kitchen.ticket.serve", {"ticket_id": str(ticket.id)})
    run("sale.order.set_label", {"order_id": str(order.id), "label": "Table 2"})
    save_everything()
    served = run("kitchen.ticket.list", {"search": "Table 9"}).rows
    assert [(row.id, row.label, row.status) for row in served] == [(ticket.id, "Table 9", "served")]


def test_a_round_whose_dishes_went_to_two_checks_with_two_titles_keeps_its_own(clock, product):
    order = open_check("Table 8")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    fries = ticket.items[1].id
    split = run("sale.order.split", {"order_id": str(order.id), "line_ids": [str(fries)], "label": "Table 8"})
    assert labels(order.id) == ["Table 8"]

    run("sale.order.set_label", {"order_id": str(split.new_order.id), "label": "Table 3"})

    assert labels(order.id) == ["Table 8"]
    assert labels(split.new_order.id) == ["Table 8"]


def test_retitling_a_check_in_b_never_touches_a_round_of_a(hub_b, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    in_b = ctx_for(scope=B)
    with use_hub(hub_b):
        dish = run(
            "inventory.product.create",
            {"name": "Soup", "sku": "SOUP", "price": 900, "tax_category_key": "restaurant.food"},
            in_b,
        )
        other = open_check("Table 4", ctx=in_b)
        add_line(other.id, dish, ctx=in_b)
        run("kitchen.ticket.send", {"order_id": str(other.id)}, in_b)
        run("sale.order.set_label", {"order_id": str(other.id), "label": "Table 9"}, in_b)
        run("kitchen.ticket.sync", {}, system_context(B))
        moved = run("kitchen.ticket.by_order", {"order_id": str(other.id)}, in_b).tickets
        assert [t.label for t in moved] == ["Table 9"]
    assert labels(order.id) == ["Table 4"]
    assert Ticket.objects.get(pk=ticket.id).label == "Table 4"
