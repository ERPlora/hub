"""A real kitchen order printed by name (PRINTING-F10, F11): the round the till sends with «Send order»
(``kitchen.ticket.send``, which Sales' till calls) and its «Reprint» (``kitchen.ticket.reprint``) go
through Kitchen's own operations, which call ``printing.job.create`` by name inside their transaction
(KITCHEN-F08, F09). No mocks: Sales opens the check, Inventory owns the products, Kitchen routes the
dishes to its stations and Printing queues one sheet per printer.
"""

import pytest
from live.context import system_context

from apps.kitchen.models import Destination
from apps.kitchen.tests.conftest import add_line, make_station, open_check, route_product
from apps.printing.models import PrintJob
from apps.printing.tests.conftest import A, ctx_for, printer, run

pytestmark = pytest.mark.django_db


def dish(name: str):
    sku = name.upper().replace(" ", "-")[:20]
    data = {"name": name, "sku": sku, "price": 1200, "tax_category_key": "restaurant.food"}
    return run("inventory.product.create", data, system_context(A))


def send(order_id, **more):
    """«Send order» of the till: Kitchen opens the round and asks Printing for its sheets."""
    return run("kitchen.ticket.send", {"order_id": str(order_id), **more}, ctx_for(actor="waiter"))


def sheets() -> list[PrintJob]:
    return list(PrintJob.objects.select_related("printer").order_by("created_at", "id"))


def test_the_order_comes_out_on_the_printer_of_each_station():
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    printer("Bar printer", usage="bar", address="10.0.0.3")
    bar = make_station("Bar", destination=Destination.PRINTER, printer_usage="bar")
    order = open_check("Table 4")
    add_line(order.id, dish("Burger"))
    beer = dish("Beer")
    route_product(beer.id, bar)
    add_line(order.id, beer)
    ticket = send(order.id)
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


def test_an_order_without_a_kitchen_printer_waits_for_one():
    printer("Till")
    order = open_check("Table 4")
    add_line(order.id, dish("Burger"))
    send(order.id)
    (job,) = sheets()
    assert (job.usage, job.printer, job.status) == ("kitchen", None, "pending")
    summary = {row.usage: row for row in run("printing.job.summary").usages}
    assert (summary["kitchen"].printers, summary["kitchen"].pending) == (0, 1)


def test_a_reprint_is_a_new_sheet_marked_copy_each_time():
    printer("Grill printer", usage="kitchen", address="10.0.0.2")
    order = open_check("Table 4")
    add_line(order.id, dish("Burger"))
    ticket = send(order.id)
    for _ in range(2):
        run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    first, *copies = sheets()
    assert first.document["duplicate"] is False
    assert [job.document["duplicate"] for job in copies] == [True, True]
    # Another key every time: the queue keeps them as three jobs, never one.
    assert len({job.job_key for job in sheets()}) == 3
    assert all(job.printer.name == "Grill printer" for job in sheets())
