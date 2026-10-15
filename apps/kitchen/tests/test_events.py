"""The kitchen app's events and its reactions to Sales' events (WORKBOOK «Lo que avisa», «A qué
reacciona»).

Cases from the old module's tests: tickets.hub (a fired round opens its ticket), closed_check.hub
(charging serves the ready rounds, leaves what cooks), voided_or_merged_check.hub (a voided check
cancels its rounds), line_voided.hub (a voided line strikes its dish). Each reaction runs as the system
through an operation of this app; delivering it twice changes nothing.
"""

import pytest

from apps.kitchen import events
from apps.kitchen.models import LogEntry, Ticket, TicketItem

from .conftest import A, add_line, charge, fire, fired_round, open_check, run

pytestmark = pytest.mark.django_db


def last_payload(name: str) -> dict:
    from live.models import OutboxEvent

    return OutboxEvent.objects.filter(name=name).latest("created_at", "id").payload


def test_every_event_is_named_app_entity_fact():
    assert events.ALL == [
        "kitchen.ticket.received",
        "kitchen.ticket.created",
        "kitchen.ticket.started",
        "kitchen.ticket.ready",
        "kitchen.ticket.served",
        "kitchen.ticket.recalled",
        "kitchen.ticket.cancelled",
        "kitchen.ticket.deleted",
        "kitchen.ticket.updated",
        "kitchen.ticket.reprinted",
        "kitchen.item.bumped",
        "kitchen.item.recalled",
        "kitchen.item.voided",
        "kitchen.station.created",
        "kitchen.station.updated",
        "kitchen.station.deleted",
        "kitchen.routing.changed",
        "kitchen.settings.updated",
    ]


def test_the_reactions_are_the_workbooks():
    assert events.REACTIONS == {
        "sale.order.fired": "kitchen.ticket.receive",
        "sale.order.completed": "kitchen.ticket.sync",
        "sale.order.voided": "kitchen.ticket.sync",
        "sale.order.line_voided": "kitchen.ticket.sync",
    }


def test_an_event_without_a_reaction_does_nothing():
    assert events.react(A, "sale.order.opened", {"order_id": "x"}) is None


def test_a_fired_round_opens_its_ticket_once(clock, product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    fire(order.id, priority="urgent")
    payload = last_payload("sale.order.fired")
    first = events.react(A, "sale.order.fired", payload).ticket
    events.react(A, "sale.order.fired", payload)
    assert (first.priority, Ticket.objects.count()) == ("rush", 1)


def test_a_charged_check_serves_its_ready_round_once(clock, product):
    order, lines = fired_round(product, "Burger")
    run("kitchen.ticket.ready", {"ticket_id": str(lines[0].id)})
    clock.advance(minutes=1)
    charge(order.id, key="event-charge")
    payload = last_payload("sale.order.completed")
    assert events.react(A, "sale.order.completed", payload).changed == 1
    assert events.react(A, "sale.order.completed", payload).changed == 0
    assert Ticket.objects.get().status == "served"
    assert LogEntry.objects.filter(action="served").count() == 1


def test_a_voided_check_cancels_its_rounds(clock, product):
    order, _ = fired_round(product, "Burger")
    run("sale.order.void", {"order_id": str(order.id)})
    events.react(A, "sale.order.voided", last_payload("sale.order.voided"))
    assert Ticket.objects.get().status == "cancelled"


def test_a_voided_line_strikes_its_dish(clock, product):
    order, lines = fired_round(product, "Burger", "Fries")
    run(
        "sale.order.void_line",
        {
            "order_id": str(order.id),
            "line_id": str(lines[0].id),
            "reason": "Wrong table",
        },
    )
    events.react(A, "sale.order.line_voided", last_payload("sale.order.line_voided"))
    item = TicketItem.objects.get(pk=lines[0].id)
    assert (item.status, item.void_reason) == ("voided", "Wrong table")
