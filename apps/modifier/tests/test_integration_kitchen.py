"""The options of a dish reach the kitchen through the real Sales, the worker's relay and Kitchen (MODIFIER-F08).

Modifiers gives, when it values the options chosen (``modifier.selection.resolve``), the kitchen text: each
option by its kitchen name (its name when it has none), in the order chosen. Sales freezes it on the line and
fires the round (``sale.order.fired``); one tick of the worker's real loop hands it to Kitchen
(``kitchen.ticket.receive``), which paints it under the dish on the card and one line each on paper. Nothing
is called by hand, and what Modifiers changes afterwards —an option renamed or deleted— never rewrites what the
cook already has. A round fired in hub B is heard in B only.

Traps of the old product: hub#1156 (the paper lost the options that the row had) and hub#1138 (the options
went chained in the note and, with several, the indent was lost: here a list, one line each).
"""

import pytest
from live.context import OperationContext
from live.meta import all_live_app_configs

from apps.kitchen.models import TicketItem
from apps.printing.models import PrintJob

from .conftest import FOOD, GENERIC, REGISTERED, A, B, heard, make_product, one_tick, run


def as_admin_of(scope, name: str, data: dict | None = None):
    """Run ``name`` in ``scope`` as a waiter holding every permission the apps declare (Sales', Kitchen's…)."""
    every = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return run(name, data or {}, ctx=OperationContext(scope=scope, actor="waiter", permissions=every, language="en"))


def option(group: str, name: str, scope=A, **fields) -> str:
    return str(as_admin_of(scope, "modifier.option.create", {"group": group, "name": name, **fields}).id)


def fired(sku: str, *option_ids: str, scope=A, notes: str = "", quantity: str = "1"):
    """A check with one line of ``sku`` and its options, fired to the kitchen by Sales."""
    order = as_admin_of(scope, "sale.order.open", {"label": "Table 4"})
    line = {"order_id": str(order.id), "product": sku, "quantity": quantity, "option_ids": list(option_ids)}
    if notes:
        line["notes"] = notes
    as_admin_of(scope, "sale.order.add_line", line)
    as_admin_of(scope, "sale.order.fire", {"order_id": str(order.id)})
    return order


def board(scope=A):
    return as_admin_of(scope, "kitchen.ticket.board", {}).cooking


def kitchen_sheets() -> list[PrintJob]:
    return list(PrintJob.objects.filter(document_type="kitchen_order").order_by("created_at", "id"))


@pytest.fixture
def burger(db):
    """A burger with «Extras» (cheese «+CHEESE» that may repeat, no onion «-ONION», a soda on a line of its own at
    21 %) and «Doneness» (rare, well done: no kitchen name, the cook reads its name)."""
    make_product("Burger", "BUR", 800, FOOD)
    run("modifier.group.create", {"name": "Extras", "max_choices": 4, "allow_repeat": True})
    run("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1})
    ids = {
        "cheese": option("Extras", "Cheese", kitchen_name="+CHEESE", price_delta=100),
        "onion": option("Extras", "No onion", kitchen_name="-ONION"),
        "soda": option("Extras", "Soda", price_delta=200, tax_category_key=GENERIC),
        "rare": option("Doneness", "Rare"),
    }
    for group in ("Extras", "Doneness"):
        run("modifier.link.attach", {"group": group, "product": "BUR"})
    return ids


def test_the_kitchen_names_of_the_options_reach_the_card_and_the_paper_through_the_relay(tick, burger):
    ids = burger
    # Not the catalogue's order (Doneness before Extras, cheese before soda): the order the waiter tapped them.
    chosen = [ids["soda"], ids["cheese"], ids["rare"], ids["onion"]]
    assert run("modifier.selection.resolve", {"product": "BUR", "option_ids": chosen}).kitchen_text == (
        "Soda, +CHEESE, Rare, -ONION"
    )
    fired("BUR", *chosen, notes="Allergic to nuts")
    assert TicketItem.objects.count() == 0  # nothing reaches the kitchen until the relay hands it over

    tick()

    (ticket,) = board()
    (item,) = ticket.items
    # Each option by its kitchen name (its name when it has none), in the order chosen; then the note.
    assert (item.name, item.modifiers, item.notes) == ("Burger", ["Soda", "+CHEESE", "Rare", "-ONION"], "Allergic to nuts")
    (sheet,) = kitchen_sheets()
    assert sheet.document["items"] == [
        {"name": "Burger", "quantity": 1.0, "modifiers": ["Soda", "+CHEESE", "Rare", "-ONION"], "notes": "Allergic to nuts"}
    ]


def test_a_repeated_option_is_on_the_ticket_as_many_times_as_it_was_chosen(tick, burger):
    ids = burger
    fired("BUR", ids["rare"], ids["cheese"], ids["cheese"], quantity="2")

    tick()

    (ticket,) = board()
    assert [(item.quantity, item.modifiers) for item in ticket.items] == [(2, ["Rare", "+CHEESE", "+CHEESE"])]


def test_renaming_or_deleting_an_option_after_the_round_never_rewrites_the_ticket(tick, burger):
    ids = burger
    fired("BUR", ids["rare"], ids["cheese"])
    run("modifier.option.update", {"id": ids["cheese"], "kitchen_name": "+EXTRA CHEESE"})
    run("modifier.option.delete", {"id": ids["rare"]})

    tick()

    (ticket,) = board()
    assert [item.modifiers for item in ticket.items] == [["Rare", "+CHEESE"]]
    # Deleting the whole group later changes nothing either.
    run("modifier.group.delete", {"group": "Extras"})
    assert list(TicketItem.objects.values_list("modifiers", flat=True)) == [["Rare", "+CHEESE"]]


def test_a_dish_without_options_carries_none_on_card_or_paper(tick, burger):
    make_product("Fries", "FRI", 300, FOOD)
    fired("FRI")

    tick()

    (ticket,) = board()
    assert [item.modifiers for item in ticket.items] == [[]]
    (sheet,) = kitchen_sheets()
    assert sheet.document["items"] == [{"name": "Fries", "quantity": 1.0}]


def test_a_round_with_options_fired_in_hub_b_is_heard_in_b_only(listen, monkeypatch):
    from base import catalog

    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    on_a, on_b = listen(A), listen(B)
    as_admin_of(B, "inventory.product.create", {"name": "Burger", "sku": "BUR-B", "price": 800, "tax_category_key": FOOD})
    as_admin_of(B, "modifier.group.create", {"name": "Extras B"})
    cheese = option("Extras B", "Cheese", scope=B, kitchen_name="+CHEESE", price_delta=100)
    as_admin_of(B, "modifier.link.attach", {"group": "Extras B", "product": "BUR-B"})
    fired("BUR-B", cheese, scope=B)
    heard(on_a), heard(on_b)  # the setup's and the round's own notices

    one_tick()

    (item,) = TicketItem.objects.all()
    assert item.modifiers == ["+CHEESE"]
    assert any(name.startswith("kitchen.") for name in heard(on_b))
    assert heard(on_a) == set()
