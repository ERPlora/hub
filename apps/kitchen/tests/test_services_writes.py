"""What the kitchen's writes could not print is logged under one logger, ``apps.kitchen.services``, whichever of
its modules it happens in."""

import logging

from apps.kitchen.models import KitchenSettings

from .conftest import HUB_DB, add_line, ctx_for, open_check, run

pytestmark = HUB_DB


def test_what_could_not_be_printed_is_logged_under_the_kitchen_writes(clock, product, printers, caplog):
    # The till voids the last dish still to cook: its void slip and the pass of the ticket, now ready, are refused by
    # Printing for a caller without its permissions.
    KitchenSettings.objects.update(print_pass=True)
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    add_line(order.id, product("Fries"))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    burger, fries = (item.id for item in ticket.items)
    run("kitchen.item.bump", {"ticket_id": str(ticket.id), "item_ids": [str(burger)]})
    clock.advance(minutes=1)
    run("sale.order.void_line", {"order_id": str(order.id), "line_id": str(fries), "reason": "Cold"})
    with caplog.at_level(logging.WARNING):
        run("kitchen.ticket.sync", {}, ctx_for(permissions={"kitchen.system"}))
    said = sorted(
        (record.getMessage().split(" of ")[0], record.name)
        for record in caplog.records
        if record.getMessage().startswith("kitchen: ")
    )
    assert said == [("kitchen: the pass", "apps.kitchen.services"), ("kitchen: the void slip", "apps.kitchen.services")]
