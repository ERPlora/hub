"""What the kitchen's writes could not print is logged under one logger, ``apps.kitchen.services``, whichever of
its modules it happens in."""

import logging

from apps.kitchen.models.settings import KitchenSettings

from .conftest import HUB_DB, ctx_for, run, void_the_last_dish_to_cook

pytestmark = HUB_DB


def test_what_could_not_be_printed_is_logged_under_the_kitchen_writes(clock, product, printers, caplog):
    # The till voids the last dish still to cook: its void slip and the pass of the ticket, now ready, are refused by
    # Printing for a caller without its permissions.
    KitchenSettings.objects.update(print_pass=True)
    void_the_last_dish_to_cook(product, clock)
    with caplog.at_level(logging.WARNING):
        run("kitchen.ticket.sync", {}, ctx_for(permissions={"kitchen.system"}))
    said = sorted(
        (record.getMessage().split(" of ")[0], record.name)
        for record in caplog.records
        if record.getMessage().startswith("kitchen: ")
    )
    assert said == [("kitchen: the pass", "apps.kitchen.services"), ("kitchen: the void slip", "apps.kitchen.services")]
