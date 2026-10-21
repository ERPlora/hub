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

from .conftest import (
    A,
    add_line,
    charge,
    fire,
    fired_round,
    make_station,
    open_check,
    route_product,
    run,
)

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


# ── Through the worker's relay, as production delivers them (hub#105) ────────────────────────────


def delivery(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to the kitchen."""
    from live.models import OutboxEvent

    from base.models import EventDelivery

    event = OutboxEvent.objects.filter(name=name).latest("created_at", "id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="kitchen")
    return row.status, row.attempts


def kitchen_sheets() -> list[str]:
    """The keys of the kitchen's sheets queued in Printing, in order."""
    from apps.printing.models import PrintJob

    return list(
        PrintJob.objects.filter(source_app="kitchen")
        .order_by("created_at", "id")
        .values_list("job_key", flat=True)
    )


def saved(ticket_id) -> str:
    return Ticket.objects.get(pk=ticket_id).status


def test_a_round_sales_fires_alone_is_saved_and_printed_by_the_relay_once(relay, clock, product):
    """KITCHEN-F05, F08: Sales' command only records ``sale.order.fired``; the tick opens the ticket with its
    priority, its History and its sheet; a second tick changes nothing."""
    order = open_check("Table 4")
    line = add_line(order.id, product("Burger")).lines[0]
    fire(order.id, priority="urgent")
    assert (Ticket.objects.count(), kitchen_sheets()) == (0, [])

    relay()

    ticket = Ticket.objects.get()
    assert (ticket.id, ticket.label, ticket.priority, ticket.printed_at is not None) == (line.id, "Table 4", "rush", True)
    assert list(LogEntry.objects.values_list("action", flat=True)) == ["received"]
    assert len(kitchen_sheets()) == 1
    assert delivery("sale.order.fired") == ("delivered", 1)

    relay()
    assert (Ticket.objects.count(), len(kitchen_sheets()), LogEntry.objects.count()) == (1, 1, 1)


def test_a_beer_sold_at_the_bar_without_a_table_prints_at_the_bar_never_as_takeaway(relay, product):
    """KITCHEN-F04, F05, F08 (kitchen#148): a drink routed to the bar, fired with no title and no channel, opens
    a «dine in» ticket whose sheet goes to the bar's printer, never the kitchen's nor as «takeaway»."""
    from apps.printing.models import PrintJob

    bar = make_station("Bar", destination="printer", printer_usage="bar")
    beer = product("Beer")
    route_product(beer.id, bar)
    order = open_check("")
    add_line(order.id, beer)
    fire(order.id)

    relay()

    ticket = Ticket.objects.get()
    assert (ticket.order_type, ticket.label) == ("dine_in", "")
    sheets = PrintJob.objects.filter(source_app="kitchen")
    assert list(sheets.values_list("usage", flat=True)) == ["bar"]


def test_a_round_the_kitchen_sends_is_not_printed_twice_when_the_relay_brings_its_fire(relay, product):
    """KITCHEN-F18, F08: the send prints its sheet in its own transaction; the relay later hands the kitchen the
    same round (``sale.order.fired``), and the queue keeps one sheet per printer."""
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id), "priority": "rush"})
    sheets = kitchen_sheets()
    assert len(sheets) == 1

    relay()

    assert delivery("sale.order.fired") == ("delivered", 1)
    assert kitchen_sheets() == sheets
    assert (saved(ticket.id), Ticket.objects.get().priority) == ("pending", "rush")


def test_charging_the_whole_check_serves_its_ready_round_through_the_relay(relay, clock, product):
    """KITCHEN-F27: the tick brings the charge; the ready round is served once, the one that cooks is left, and a
    check charged only in part closes nothing."""
    order, lines = fired_round(product, "Burger")
    cooking, cooking_lines = fired_round(product, "Soup", label="Table 5")
    partial, partial_lines = fired_round(product, "Salad", "Water", label="Table 6")
    for ticket_id in (lines[0].id, partial_lines[0].id):
        run("kitchen.ticket.ready", {"ticket_id": str(ticket_id)})
    clock.advance(minutes=1)
    charge(order.id, key="relay-whole")
    charge(cooking.id, key="relay-cooking")
    charge(partial.id, key="relay-partial", line_ids=[partial_lines[0].id])
    assert saved(lines[0].id) == "ready"

    relay()

    assert delivery("sale.order.completed") == ("delivered", 1)
    assert (saved(lines[0].id), saved(cooking_lines[0].id), saved(partial_lines[0].id)) == ("served", "pending", "ready")
    assert LogEntry.objects.filter(action="served").count() == 1
    relay()
    assert LogEntry.objects.filter(action="served").count() == 1


def test_voiding_a_check_cancels_its_rounds_through_the_relay(relay, clock, product):
    """KITCHEN-F28: the tick brings the voided check; its round on the line is cancelled with its History."""
    order, lines = fired_round(product, "Burger")
    run("kitchen.ticket.start", {"ticket_id": str(lines[0].id)})
    run("sale.order.void", {"order_id": str(order.id)})
    assert saved(lines[0].id) == "preparing"

    relay()

    assert delivery("sale.order.voided") == ("delivered", 1)
    assert saved(lines[0].id) == "cancelled"
    assert LogEntry.objects.filter(ticket_id=lines[0].id, action="cancelled").count() == 1


def test_a_printed_round_whose_check_is_deleted_in_the_till_prints_its_cancel_slip_through_the_relay(
    relay, clock, product
):
    """KITCHEN-F22, F28 (kitchen#168): the round went to paper; deleting its check in the till cancels it, and the
    tick prints the «CANCELLED» slip of what was left, so the kitchen stops cooking it."""
    from apps.printing.models import PrintJob

    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    relay()
    run("sale.order.void", {"order_id": str(order.id)})

    relay()

    assert (saved(ticket.id), delivery("sale.order.voided")) == ("cancelled", ("delivered", 1))
    sheets = list(PrintJob.objects.filter(source_app="kitchen").order_by("created_at", "id"))
    assert len(sheets) == 2
    slip = sheets[-1].document
    assert (slip["label"], [(i["name"], i["quantity"]) for i in slip["items"]]) == (
        "CANCELLED · Table 4",
        [("Burger", -1.0)],
    )


def test_a_line_voided_in_the_till_strikes_its_dish_and_prints_its_slip_through_the_relay(relay, clock, product):
    """KITCHEN-F29 (hub#2640): the tick brings the voided line; its dish is struck with the reason, the rest of the
    round cooks on, and the station that had it on paper gets its void slip."""
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    burger = ticket.items[0].id
    run(
        "sale.order.void_line",
        {"order_id": str(order.id), "line_id": str(burger), "reason": "Wrong table"},
    )
    assert TicketItem.objects.get(pk=burger).status == "pending"

    relay()

    assert delivery("sale.order.line_voided") == ("delivered", 1)
    item = TicketItem.objects.get(pk=burger)
    assert (item.status, item.void_reason) == ("voided", "Wrong table")
    assert saved(ticket.id) == "pending"
    assert [key for key in kitchen_sheets() if f"-void-{burger}-" in key] != []
    assert LogEntry.objects.filter(action="item_voided", notes="Wrong table").count() == 1
