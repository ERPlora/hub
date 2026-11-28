"""The assistant seats a parked check at a table again: a party that went to the bar with its check parked
(TABLE-F13) wants to sit down again, and the assistant brings that check of Sales to a free table with
``table.session.open`` (TABLE-F12). It sits again as «Seat again» does it (TABLE-F24): the same table check,
with its guests, waiter and opening time, never a refusal saying the check is «at table Parked»."""

import json

import pytest
from live.operations import get

from apps.sale.models import Order
from apps.table.models import TableSession
from base import assistant

from .conftest import HUB_DB, add_line, ctx_for, make_table, make_zone, open_check, run
from .test_services import MANAGER, names

pytestmark = HUB_DB


@pytest.fixture
def parked_beers(product):
    """Table 9's check with two beers, parked when the couple moved to the bar; table 3 is free."""
    room = make_zone("Sala")
    nine, three = make_table("9", zone=room, capacity=4), make_table("3", zone=room, capacity=2)
    order = open_check()
    add_line(order.id, product(name="Caña", sku="CANA"), quantity="2")
    seated = run("table.session.open", {"table_id": str(nine.id), "order_id": str(order.id), "guests_count": 2})
    run("table.session.park", {"id": str(seated.id)})
    return {"order": order, "session": seated, "nine": nine, "three": three}


def by_order(order_id):
    rows = run("table.session.by_order", {"order_id": str(order_id)}).rows
    return [(row.id, row.table_number, row.status) for row in rows]


def test_the_assistant_seats_a_parked_check_at_a_free_table_as_seat_again_does(parked_beers):
    """«Put their tab on table 3»: the assistant brings the parked check of Sales to table 3 and it sits there."""
    order, session = parked_beers["order"], parked_beers["session"]
    arguments = {"table": "3", "order_id": str(order.id)}

    outcome = assistant.tools.run(ctx_for(MANAGER, language="es"), get("table.session.open"), json.dumps(arguments))

    assert outcome.outcome == "ok", outcome.content
    assert by_order(order.id) == [(session.id, "3", "open")]
    again = TableSession.objects.get(pk=session.id)
    assert (again.guests_count, again.opened_at, again.waiter_name) == (2, session.opened_at, session.waiter_name)
    assert Order.objects.get(pk=order.id).label == "Mesa 3"
    assert Order.objects.count() == 1
    assert run("table.table.get", {"id": str(parked_beers["nine"].id)}).status == "available"
    assert names()[-1] == "table.session.restored"


def test_the_card_of_seating_a_parked_check_names_the_table_and_the_check(parked_beers):
    """What the person confirms, in Spanish: the table it sits at and the check of Sales by its title."""
    arguments = {"table": "3", "order_id": str(parked_beers["order"].id)}

    shown = assistant.cards.card(get("table.session.open"), arguments, "es", ctx=ctx_for(MANAGER, language="es"))

    assert [(field["label"], field["value"]) for field in shown["fields"]] == [
        ("Mesa", "3"),
        ("Cuenta de Ventas", "Table 9"),
    ]


def test_a_parked_check_is_not_linked_to_another_table_and_the_refusal_never_calls_parked_a_table(parked_beers):
    """Linking the parked check of Sales to a table that already has its own check is refused in words that say
    it is parked and how it sits again, never «already at table Parked»."""
    other = run("table.session.open", {"table_id": str(parked_beers["three"].id)})
    TableSession.objects.filter(pk=other.id).update(order_id=None)
    arguments = {"table": "3", "order_id": str(parked_beers["order"].id)}

    outcome = assistant.tools.run(ctx_for(MANAGER), get("table.session.link_order"), json.dumps(arguments))

    assert outcome.outcome == "error"
    assert "table.order_parked" in outcome.content
    assert "Parked." not in outcome.content



def test_a_parked_check_already_charged_in_sales_is_not_seated_by_bringing_it(parked_beers):
    """A parked check whose check of Sales was charged meanwhile stays off the floor: bringing it to a table is
    refused as no longer open, and the table stays free."""
    order = parked_beers["order"]
    Order.objects.filter(pk=order.id).update(status=Order.Status.COMPLETED)
    arguments = {"table": "3", "order_id": str(order.id)}

    outcome = assistant.tools.run(ctx_for(MANAGER), get("table.session.open"), json.dumps(arguments))

    assert outcome.outcome == "error"
    assert "table.order_not_open" in outcome.content
    assert run("table.table.get", {"id": str(parked_beers["three"].id)}).status == "available"
