"""Kitchen with the real Sales and Modifiers: the options chosen for a dish reach the cook (KITCHEN-F07).

The waiter picks the options of a line in the till (SALE-F11, Modifiers' ``modifier.selection.resolve``),
Sales freezes them on the line and fires the round (``sale.order.fired``), and the worker's relay hands it
to the kitchen (``kitchen.ticket.receive``), as production runs it: nothing is called by hand. Each option
reaches the dish by its kitchen name, in the order chosen, under the dish on the card and as one line each
on paper, with the waiter's note after them.

Traps of the old product: pm#93 and sales#237 (the chain of options till → ticket → kitchen, end to end),
hub#1156 (the paper lost the options that the row had), kitchen#64 (the options travel to paper as a LIST,
one line each, never a joined string), sales#156 and pm#115 (the note of the line, the only place an allergy
lives, reaches card and paper).
"""

import pytest
from live.context import system_context

from apps.kitchen.models import TicketItem

from .conftest import A, add_line, fire, open_check, run

pytestmark = pytest.mark.django_db

FOOD = "restaurant.food"
GENERIC = "product.generic"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture
def burger(product):
    """A burger with its «Extras» (cheese «+CHEESE», no onion «-ONION», a soda charged on a line of its
    own) and its «Doneness» (rare, well done; no kitchen name: the cook reads its name)."""
    dish = product("Burger", "BUR", 800, FOOD)
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4})
    setup("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1})
    options = {
        "cheese": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "Cheese", "kitchen_name": "+CHEESE", "price_delta": 100},
        ),
        "onion": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "No onion", "kitchen_name": "-ONION"},
        ),
        "soda": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "Soda", "price_delta": 200, "tax_category_key": GENERIC},
        ),
        "rare": setup("modifier.option.create", {"group": "Doneness", "name": "Rare"}),
    }
    for group in ("Extras", "Doneness"):
        setup("modifier.link.attach", {"group": group, "product_id": str(dish.id)})
    return dish, {key: str(option.id) for key, option in options.items()}


def kitchen_sheets():
    from apps.printing.models import PrintJob

    return list(
        PrintJob.objects.filter(document_type="kitchen_order").order_by("created_at", "id")
    )


def test_the_options_of_a_dish_reach_its_card_and_its_paper_through_the_relay(relay, burger):
    dish, options = burger
    order = open_check("Table 4")
    add_line(
        order.id,
        dish,
        option_ids=[options["cheese"], options["onion"], options["soda"], options["rare"]],
        notes="Allergic to nuts",
    )
    fire(order.id)
    assert TicketItem.objects.count() == 0

    relay()

    (ticket,) = run("kitchen.ticket.board", {}).cooking
    (item,) = ticket.items
    # Each option by its kitchen name (its name when it has none), in the order chosen; then the note.
    assert (item.name, item.modifiers, item.notes) == (
        "Burger",
        ["+CHEESE", "-ONION", "Soda", "Rare"],
        "Allergic to nuts",
    )
    # Frozen on the dish: renaming the option in the catalogue tomorrow does not rewrite this ticket.
    setup("modifier.option.update", {"id": options["cheese"], "kitchen_name": "+EXTRA CHEESE"})
    (saved,) = TicketItem.objects.all()
    assert saved.modifiers == ["+CHEESE", "-ONION", "Soda", "Rare"]

    # On paper, the options as a list (one line each) and the note after them.
    (sheet,) = kitchen_sheets()
    assert sheet.document["items"] == [
        {
            "name": "Burger",
            "quantity": 1.0,
            "modifiers": ["+CHEESE", "-ONION", "Soda", "Rare"],
            "notes": "Allergic to nuts",
        }
    ]


def test_a_dish_without_options_carries_none_on_card_or_paper(relay, product):
    order = open_check("Table 4")
    add_line(order.id, product("Fries"))
    fire(order.id)

    relay()

    (ticket,) = run("kitchen.ticket.board", {}).cooking
    assert [item.modifiers for item in ticket.items] == [[]]
    (sheet,) = kitchen_sheets()
    assert sheet.document["items"] == [{"name": "Fries", "quantity": 1.0}]
