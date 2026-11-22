"""The customer's allergy reaches the kitchen (KITCHEN-F32): the waiter marks it on a line in the till (SALE-F41), and
when the round arrives each dish keeps, frozen, that allergy and those of its allergens the dish contains (in a menu,
dish by dish). The board, the ticket and the paper say it; a ticket made by hand has none. Inventory, Menus, Sales and
Printing are the real apps.
"""

import dataclasses
import uuid

import pytest
from django.db import connections
from django.utils import timezone
from live.context import system_context
from pydantic import ValidationError

from apps.kitchen.models import KitchenSettings, Ticket, TicketItem
from apps.kitchen.queries.rounds import unsaved_views
from apps.kitchen.queries.views import saved_views
from apps.sale.models import OrderLine
from base.models import Hub
from base.tenancy.context import current_alias

from .conftest import HUB_DB, A, add_line, ctx_for, fire, make_station, open_check, route_product, run

pytestmark = HUB_DB

FOOD = "restaurant.food"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture
def kitchen(product):
    """A burger with gluten, milk and sesame, a salad with none and a beer that goes to the bar; «Burger menu», the
    burger and a flan with egg and milk."""
    products = {
        "burger": product("Burger", "BUR", 1200, FOOD, allergens=["sesame", "milk", "gluten"]),
        "salad": product("Salad", "SAL", 800, FOOD),
        "beer": product("Beer", "BEE", 300, FOOD),
        "flan": product("Flan", "FLA", 400, FOOD, allergens=["milk", "egg"]),
    }
    route_product(products["beer"].id, make_station("Bar", printer_usage="bar"))
    setup("combo.combo.create", {"name": "Burger menu", "price": 1400, "tax_category_key": FOOD})
    options = []
    for group, sku in (("Main", "BUR"), ("Dessert", "FLA")):
        setup("combo.group.create", {"combo": "Burger menu", "name": group})
        option = setup("combo.option.create", {"combo": "Burger menu", "group": group, "product": sku})
        options.append({"option_id": str(option.id)})
    return {**products, "menu": options}


def mark(order_id, line_id, allergy: list[str]) -> None:
    data = {"order_id": str(order_id), "line_id": str(line_id), "allergy": allergy}
    run("sale.order.set_line_allergy", data, ctx_for(actor="waiter"))


def check_with(kitchen, *marked: tuple[str, list[str]]):
    """An open check with a line of each ``(product, allergy)``, the allergy marked when there is one."""
    order = open_check("Table 4")
    for name, allergy in marked:
        line = add_line(order.id, kitchen[name]).lines[-1]
        if allergy:
            mark(order.id, line.id, allergy)
    return order


def menu_check(kitchen, allergy: list[str]):
    order = open_check("Table 4")
    data = {"order_id": str(order.id), "combo": "Burger menu", "choices": kitchen["menu"]}
    line = run("sale.order.add_combo_line", data, ctx_for(actor="waiter")).lines[-1]
    mark(order.id, line.id, allergy)
    return order


def receive(order) -> list[TicketItem]:
    fire(order.id)
    run("kitchen.ticket.sync", {}, system_context(A))
    return list(TicketItem.objects.order_by("position"))


def frozen(items) -> list[tuple[str, list[str], list[str]]]:
    return [(item.name, item.allergy, item.allergy_in_dish) for item in items]


def jobs():
    from apps.printing.models import PrintJob

    return list(PrintJob.objects.order_by("created_at", "id"))


def sheets() -> dict[str, dict]:
    return {job.usage: job.document for job in jobs()}


def speaks(language: str) -> None:
    Hub.objects.filter(slug=A.key).update(language=language)


# ── What a dish keeps ────────────────────────────────────────────────────────────────────────────


def test_a_received_dish_keeps_the_customers_allergy_and_what_of_it_the_dish_contains(kitchen):
    order = check_with(kitchen, ("burger", ["fish", "gluten"]), ("salad", ["gluten"]), ("beer", []))
    assert frozen(receive(order)) == [
        ("Burger", ["gluten", "fish"], ["gluten"]),
        ("Salad", ["gluten"], []),
        ("Beer", [], []),
    ]


def test_an_allergen_only_an_option_brings_counts_as_the_dishs(kitchen):
    """A salad declares none, but «+Cheese» brings milk: the cook reads that the dish contains it."""
    setup("modifier.group.create", {"name": "Extras"})
    cheese = setup("modifier.option.create", {"group": "Extras", "name": "Cheese", "allergens": ["milk"]})
    setup("modifier.link.attach", {"group": "Extras", "product_id": str(kitchen["salad"].id)})
    order = open_check("Table 4")
    line = add_line(order.id, kitchen["salad"], option_ids=[str(cheese.id)]).lines[-1]
    mark(order.id, line.id, ["milk"])
    assert frozen(receive(order)) == [("Salad", ["milk"], ["milk"])]


def test_what_a_dish_keeps_does_not_change_when_the_catalogue_does(kitchen):
    order = check_with(kitchen, ("burger", ["milk"]))
    (dish,) = receive(order)
    setup("inventory.product.update", {"id": str(kitchen["burger"].id), "allergens": []})
    OrderLine.objects.filter(pk=dish.sale_line_id).update(allergy=[], allergens=[])
    (item,) = run("kitchen.ticket.get", {"ticket_id": str(dish.ticket_id)}).items
    assert (item.allergy, item.allergy_in_dish) == (["milk"], ["milk"])


def test_each_dish_of_a_menu_carries_the_allergy_and_its_own_allergens_that_match(kitchen):
    order = menu_check(kitchen, ["milk", "egg"])
    assert frozen(receive(order)) == [
        ("Burger", ["egg", "milk"], ["milk"]),
        ("Flan", ["egg", "milk"], ["egg", "milk"]),
    ]


def test_a_menu_ordered_before_its_dishes_kept_allergens_matches_none_of_them(kitchen):
    order = menu_check(kitchen, ["milk"])
    line = OrderLine.objects.get(order_id=order.id)
    combo = {**line.combo, "components": [{k: v for k, v in dish.items() if k != "allergens"} for dish in line.combo["components"]]}
    OrderLine.objects.filter(pk=line.pk).update(combo=combo)
    assert frozen(receive(order)) == [("Burger", ["milk"], []), ("Flan", ["milk"], [])]


def test_the_board_shows_a_round_not_saved_yet_as_the_kitchen_saves_it(kitchen):
    order = menu_check(kitchen, ["gluten"])
    add_line(order.id, kitchen["burger"])
    fire(order.id)
    (before,) = unsaved_views(KitchenSettings.objects.get())
    (shown,) = run("kitchen.ticket.board", {}).cooking
    assert [(item.allergy, item.allergy_in_dish) for item in shown.items] == [
        (["gluten"], ["gluten"]),
        (["gluten"], []),
        ([], []),
    ]
    run("kitchen.ticket.sync", {}, system_context(A))
    (after,) = saved_views(Ticket.objects.all())
    assert [dataclasses.asdict(item) for item in after.items] == [dataclasses.asdict(item) for item in before.items]


def test_a_ticket_made_by_hand_has_no_allergy_and_takes_none(kitchen):
    created = run("kitchen.ticket.create", {"label": "Staff", "items": [{"product": "Burger"}]})
    (item,) = created.items
    assert (item.allergy, item.allergy_in_dish) == ([], [])
    with pytest.raises(ValidationError):
        run("kitchen.ticket.create", {"label": "Staff", "items": [{"product": "Burger", "allergy": ["gluten"]}]})


def test_the_code_from_before_still_saves_a_dish_during_the_deploy():
    """The deploy migrates before it replaces the services: the code of before inserts dishes without the new
    columns, so they need their default in the database."""
    ticket = Ticket.objects.create(
        number="20261014-0008", day=timezone.localdate(), sequence=8, received_at=timezone.now()
    )
    dish = uuid.uuid7()
    with connections[current_alias()].cursor() as cursor:
        cursor.execute(
            "INSERT INTO kitchen_ticketitem (id, ticket_id, sale_line_id, position, name, quantity, unit, notes, "
            "station_name, destination, printer_usage, printer_name, status, void_reason, total) "
            "VALUES (%s, %s, %s, 1, 'Burger', 1, 'ud', '', '', 'both', 'kitchen', '', 'pending', '', 1200)",
            [dish, ticket.id, uuid.uuid7()],
        )
    item = TicketItem.objects.get(pk=dish)
    assert (item.allergy, item.allergy_in_dish) == ([], [])


# ── On paper ─────────────────────────────────────────────────────────────────────────────────────


def test_the_paper_marks_the_allergy_in_the_header_and_under_the_dish_in_the_businesss_language(kitchen, printers):
    speaks("es")
    order = check_with(kitchen, ("burger", ["fish", "gluten"]), ("salad", []), ("beer", []))
    run("kitchen.ticket.send", {"order_id": str(order.id)}, ctx_for(actor="luis", language="en"))
    kitchen_sheet, bar_sheet = sheets()["kitchen"], sheets()["bar"]
    assert kitchen_sheet["allergy"] == "!! ALERGIA !!"
    assert [item.get("modifiers", []) for item in kitchen_sheet["items"]] == [
        ["*** ALERGIA: GLUTEN, PESCADO ***", "*** LLEVA: GLUTEN ***"],
        [],
    ]
    assert (bar_sheet["allergy"], bar_sheet["items"][0].get("modifiers")) == ("", None)


def test_an_allergy_the_dish_does_not_contain_prints_no_contains_line(kitchen, printers):
    speaks("en")
    order = check_with(kitchen, ("burger", ["fish"]))
    run("kitchen.ticket.send", {"order_id": str(order.id)})
    sheet = sheets()["kitchen"]
    (dish,) = sheet["items"]
    assert dish["modifiers"] == ["*** ALLERGY: FISH ***"]
    assert sheet["allergy"] == "!! ALLERGY !!"


def test_each_dish_of_a_menu_prints_its_own_lines(kitchen, printers):
    speaks("en")
    order = menu_check(kitchen, ["egg"])
    run("kitchen.ticket.send", {"order_id": str(order.id)})
    assert [item["modifiers"] for item in sheets()["kitchen"]["items"]] == [
        ["*** ALLERGY: EGG ***"],
        ["*** ALLERGY: EGG ***", "*** CONTAINS: EGG ***"],
    ]


def test_the_reprint_comes_out_with_the_same_marks(kitchen, printers):
    speaks("en")
    order = check_with(kitchen, ("burger", ["milk"]))
    ticket = run("kitchen.ticket.send", {"order_id": str(order.id)})
    run("kitchen.ticket.reprint", {"ticket_id": str(ticket.id)})
    first, copy = jobs()
    assert copy.document["duplicate"] is True
    assert (copy.document["allergy"], copy.document["items"]) == (first.document["allergy"], first.document["items"])
    assert copy.document["items"][0]["modifiers"] == ["*** ALLERGY: MILK ***", "*** CONTAINS: MILK ***"]


def test_the_allergy_goes_before_the_options_the_customer_chose():
    from apps.kitchen import allergy as paper

    dish = TicketItem(name="Burger", allergy=["milk"], allergy_in_dish=["milk"])
    document = {"allergy": "", "items": [{"name": "Burger", "quantity": 1.0, "modifiers": ["+CHEESE"]}]}
    marked = paper.on_paper(document, [dish], "en")
    assert marked["items"][0]["modifiers"] == ["*** ALLERGY: MILK ***", "*** CONTAINS: MILK ***", "+CHEESE"]
    assert marked["allergy"] == "!! ALLERGY !!"
    assert document["items"][0]["modifiers"] == ["+CHEESE"]


def test_a_sheet_without_an_allergy_comes_out_as_before():
    from apps.kitchen import allergy as paper

    dish = TicketItem(name="Salad")
    document = {"items": [{"name": "Salad", "quantity": 1.0}]}
    assert paper.on_paper(document, [dish], "es") == {**document, "allergy": ""}
