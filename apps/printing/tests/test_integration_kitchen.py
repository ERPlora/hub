"""A real kitchen order printed by name (PRINTING-F10, F11): the round the till sends with «Send order»
(``kitchen.ticket.send``, which Sales' till calls) and its «Reprint» (``kitchen.ticket.reprint``) go
through Kitchen's own operations, which call ``printing.job.create`` by name inside their transaction
(KITCHEN-F08, F09). No mocks: Sales opens the check, Inventory owns the products, Kitchen routes the
dishes to its stations and Printing queues one sheet per printer. Where no active printer prints a function, the
kitchen cooks from its screen: nothing of that function is queued and the bell stays quiet.
"""

import pytest
from django.db.models import F
from live.context import system_context
from live.errors import Conflict

from apps.kitchen.models import Destination
from apps.kitchen.tests.conftest import add_line, make_station, open_check, route_product
from apps.printing.models import PrintJob
from apps.printing.queries import STALLED_AFTER
from apps.printing.tests.conftest import A, B, HUB_DB, ctx_for, printer, run
from base.tenancy.context import use_hub

pytestmark = HUB_DB


def dish(name: str):
    sku = name.upper().replace(" ", "-")[:20]
    data = {"name": name, "sku": sku, "price": 1200, "tax_category_key": "restaurant.food"}
    return run("inventory.product.create", data, system_context(A))


def waiter():
    return ctx_for(actor="waiter")


def send(order_id, **more):
    """«Send order» of the till: Kitchen opens the round and asks Printing for its sheets."""
    return run("kitchen.ticket.send", {"order_id": str(order_id), **more}, waiter())


def sheets() -> list[PrintJob]:
    return list(PrintJob.objects.select_related("printer").order_by("created_at", "id"))


def burger_and_a_beer_at_the_bar(**bar):
    """Table 4's check with a burger, which has no station, and a beer routed to the bar."""
    station = make_station("Bar", printer_usage="bar", **bar)
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    beer = dish("Beer")
    route_product(beer.id, station)
    add_line(order.id, beer, ctx=waiter())
    return order


def test_the_order_comes_out_on_the_printer_of_each_station():
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    printer("Bar printer", usage="bar", address="10.0.0.3")
    ticket = send(burger_and_a_beer_at_the_bar(destination=Destination.PRINTER).id)
    by_usage = {job.usage: job for job in sheets()}
    assert sorted(by_usage) == ["bar", "kitchen"]
    kitchen, drinks = by_usage["kitchen"], by_usage["bar"]
    # Each sheet is a kitchen order with its own dishes, on the printer of its function.
    assert (kitchen.document_type, kitchen.printer.name, kitchen.source_app, kitchen.reference) == (
        "kitchen_order",
        "Grill printer",
        "kitchen",
        ticket.number,
    )
    assert [item["name"] for item in kitchen.document["items"]] == ["Burger"]
    assert (drinks.printer.name, [item["name"] for item in drinks.document["items"]]) == ("Bar printer", ["Beer"])
    assert (kitchen.document["table"], kitchen.document["waiter"], kitchen.document["duplicate"]) == ("Table 4", "waiter", False)
    # The order never goes to the receipt printer; it waits for its own.
    assert all(job.usage != "receipt" for job in sheets())


def nothing_printing(usage: str) -> int:
    """The bell's «Nothing is printing» count of ``usage``, once whatever was queued has waited its minute."""
    PrintJob.objects.update(created_at=F("created_at") - STALLED_AFTER)
    return run("printing.device.coverage", {"usage": usage}).count


def test_a_kitchen_with_no_kitchen_printer_cooks_from_its_screen_and_the_bell_stays_quiet():
    printer("Till")
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    ticket = send(order.id)
    assert (ticket.status, ticket.print_error) == ("pending", None)
    assert nothing_printing("kitchen") == 0
    assert sheets() == []


def test_a_station_left_on_screen_and_paper_goes_to_the_screen_only_without_its_printer():
    grill = make_station("Grill")
    order = open_check("Table 4", ctx=system_context(A))
    burger = dish("Burger")
    route_product(burger.id, grill)
    add_line(order.id, burger, ctx=waiter())
    assert send(order.id).print_error is None
    assert sheets() == []


def test_an_inactive_kitchen_printer_is_no_kitchen_printer():
    grill = printer("Grill printer", usage="kitchen", address="10.0.0.2")
    run("printing.printer.update", {"printer_id": str(grill.id), "is_active": False})
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    send(order.id)
    assert sheets() == []
    assert nothing_printing("kitchen") == 0


def test_each_function_goes_to_paper_only_where_it_has_a_printer():
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    send(burger_and_a_beer_at_the_bar().id)
    (kitchen,) = sheets()
    assert (kitchen.usage, kitchen.printer.name) == ("kitchen", "Grill printer")
    assert [item["name"] for item in kitchen.document["items"]] == ["Burger"]
    assert nothing_printing("bar") == 0


def test_a_station_that_names_its_printer_prints_on_it_with_no_printer_of_its_function():
    printer("Till")
    send(burger_and_a_beer_at_the_bar(printer_name="Till").id)
    (drinks,) = sheets()
    assert (drinks.usage, drinks.printer.name) == ("bar", "Till")
    assert [item["name"] for item in drinks.document["items"]] == ["Beer"]


def test_another_business_kitchen_printer_does_not_send_this_one_to_paper(hub_b):
    with use_hub(hub_b):
        data = {"name": "Grill printer", "kind": "network", "address": "10.0.0.2", "usage": "kitchen"}
        run("printing.printer.create", data, ctx_for(scope=B))
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    send(order.id)
    assert sheets() == []


def test_reprinting_with_no_kitchen_printer_says_so_and_queues_nothing():
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    ticket = send(order.id)
    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    assert refused.value.code == "kitchen.printing_unavailable"
    assert sheets() == []


def test_a_reprint_is_a_new_sheet_marked_copy_each_time():
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    order = open_check("Table 4", ctx=system_context(A))
    add_line(order.id, dish("Burger"), ctx=waiter())
    ticket = send(order.id)
    for _ in range(2):
        run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    first, *copies = sheets()
    assert first.document["duplicate"] is False
    assert [job.document["duplicate"] for job in copies] == [True, True]
    # Another key every time: the queue keeps them as three jobs, never one.
    assert len({job.job_key for job in sheets()}) == 3
    assert all(job.printer.name == "Grill printer" for job in sheets())
