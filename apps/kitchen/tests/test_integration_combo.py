"""Kitchen with the real Sales and Menus: a menu of the day reaches the kitchen dish by dish (KITCHEN-F06).

The waiter adds a menu with its choices in the till (SALE-F12, Menus' ``combo.combo.resolve``), Sales
freezes its dishes on the line and fires the round (``sale.order.fired``), and the worker's relay hands it
to the kitchen (``kitchen.ticket.receive``), as production runs it: nothing is called by hand. Each dish
goes to the station of ITS product (else of its category: KITCHEN-F04), never to the menu's, with the
quantity times the menus ordered and under the menu's header (its kitchen name, else its name), on the
card and on paper; the menu's note on each of its dishes; the menu's amount counted once.

Traps of the old product: sales#522 and pm#94 (the kitchen got «Menu of the day» without the dishes chosen),
kitchen#57 (each dish to ITS station, grouped under the menu, as a list and never a paragraph: TouchBistro
sends the salad to the grill), hub#1156 (the paper lost the menu's header), sales#535 (a menu short of a
course never reaches the kitchen: Sales refuses it, ``apps/sale/tests/test_integration_combo.py``).
"""

from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import Conflict

from apps.kitchen.models import Ticket, TicketItem

from .conftest import (
    A,
    add_line,
    ctx_for,
    fire,
    make_station,
    open_check,
    route_category,
    route_product,
    run,
)

pytestmark = pytest.mark.django_db

FOOD = "restaurant.food"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture
def menu(product, category):
    """«Menu of the day» (kitchen name «MENU»): «Starters» (lentils or salad), «Mains» (steak, in the
    category «Grill»), an optional «Dessert» (flan) and a «Service» course of a service (a tip jar).
    Stations: «Cold» gets the lentils by product, «Grill» the category «Grill», «Pastry» the flan."""
    grill_category = category("Grill")
    products = {
        "LEN": product("Lentils", "LEN", 500, FOOD),
        "SAL": product("Salad", "SAL", 450, FOOD),
        "STK": product("Steak", "STK", 1800, FOOD, category_ids=[str(grill_category.id)]),
        "FLA": product("Flan", "FLA", 400, FOOD),
        "TIP": product("Table service", "TIP", 100, FOOD, product_type="service"),
    }
    setup(
        "combo.combo.create",
        {"name": "Menu of the day", "kitchen_name": "MENU", "price": 1350, "tax_category_key": FOOD},
    )
    for group, minimum in (("Starters", 1), ("Mains", 1), ("Dessert", 0), ("Service", 0)):
        setup(
            "combo.group.create",
            {"combo": "Menu of the day", "name": group, "min_choices": minimum},
        )
    options = {}
    for group, sku in (
        ("Starters", "LEN"),
        ("Starters", "SAL"),
        ("Mains", "STK"),
        ("Dessert", "FLA"),
        ("Service", "TIP"),
    ):
        options[sku] = str(
            setup(
                "combo.option.create",
                {"combo": "Menu of the day", "group": group, "product": sku},
            ).id
        )
    stations = {
        "cold": make_station("Cold"),
        "grill": make_station("Grill"),
        "pastry": make_station("Pastry", printer_usage="bar"),
    }
    route_product(products["LEN"].id, stations["cold"])
    route_category(grill_category.id, stations["grill"])
    route_product(products["FLA"].id, stations["pastry"])
    return options, products, stations


def add_menu(order_id, *option_ids: str, quantity: str = "1", notes: str = "", combo="Menu of the day"):
    return run(
        "sale.order.add_combo_line",
        {
            "order_id": str(order_id),
            "combo": combo,
            "choices": [{"option_id": option_id} for option_id in option_ids],
            "quantity": quantity,
            "notes": notes,
        },
        ctx_for(actor="waiter"),
    )


def board(station=None):
    return run("kitchen.ticket.board", {} if station is None else {"station": str(station.id)})


def kitchen_sheets():
    from apps.printing.models import PrintJob

    return list(
        PrintJob.objects.filter(document_type="kitchen_order").order_by("created_at", "id")
    )


def dishes(ticket) -> list[tuple]:
    return [
        (item.name, item.quantity, item.menu_name, item.station_name, item.notes)
        for item in ticket.items
    ]


def test_each_dish_of_a_menu_goes_to_its_own_station_under_the_menus_header(relay, menu, product):
    options, _, stations = menu
    order = open_check("Table 4")
    check = add_menu(order.id, options["LEN"], options["STK"], options["FLA"], quantity="2", notes="No salt")
    (menu_line,) = check.lines
    add_line(order.id, product("Burger", "BUR", 1200, FOOD))
    fire(order.id)
    assert TicketItem.objects.count() == 0

    relay()

    (ticket,) = board().cooking
    # The menu's dishes, each at the station of its own product (or its category), the quantity times the
    # menus, the menu's note on each; then the dish ordered on its own, with no header.
    assert dishes(ticket) == [
        ("Lentils", Decimal("2"), "MENU", "Cold", "No salt"),
        ("Steak", Decimal("2"), "MENU", "Grill", "No salt"),
        ("Flan", Decimal("2"), "MENU", "Pastry", "No salt"),
        ("Burger", Decimal("1"), "", "", ""),
    ]
    menu_dishes = ticket.items[:3]
    assert {item.menu_line_id for item in menu_dishes} == {menu_line.id}
    assert ticket.items[3].menu_line_id is None
    # The dishes of the menu have ids of their own (each is marked ready on its own) and none is the
    # service of the menu: a service is never cooked.
    assert len({item.id for item in ticket.items}) == 4
    assert "Table service" not in [item.name for item in ticket.items]
    # The menu's amount counts once in the ticket, with the burger's.
    assert ticket.total == menu_line.line_total + 1200

    # Each station sees only its dish, still under the menu's header.
    (grill,) = board(stations["grill"]).cooking
    assert dishes(grill) == [("Steak", Decimal("2"), "MENU", "Grill", "No salt")]


def test_on_paper_each_printer_gets_its_dishes_under_the_menus_header(relay, menu):
    options, _, _ = menu
    order = open_check("Table 4")
    (menu_line,) = add_menu(order.id, options["SAL"], options["STK"], options["FLA"]).lines
    fire(order.id)

    relay()

    sheets = {job.usage: job.document["items"] for job in kitchen_sheets()}
    ref = str(menu_line.id)
    # The salad (no station) and the steak (the grill) print on the kitchen printer, in one run under the
    # menu's header; the flan, at the bar's, with the same header over it.
    assert sheets == {
        "kitchen": [
            {"name": "Salad", "quantity": 1.0, "combo_ref": ref, "combo_name": "MENU"},
            {"name": "Steak", "quantity": 1.0, "combo_ref": ref, "combo_name": "MENU"},
        ],
        "bar": [{"name": "Flan", "quantity": 1.0, "combo_ref": ref, "combo_name": "MENU"}],
    }


def test_a_menu_without_a_kitchen_name_is_headed_by_its_name(relay, menu):
    options, _, _ = menu
    setup("combo.combo.update", {"combo": "Menu of the day", "kitchen_name": ""})
    order = open_check("Table 4")
    add_menu(order.id, options["SAL"], options["STK"])
    fire(order.id)

    relay()

    (ticket,) = board().cooking
    assert [item.menu_name for item in ticket.items] == ["Menu of the day", "Menu of the day"]


def test_two_menus_on_one_check_stay_two_groups(relay, menu):
    options, _, _ = menu
    order = open_check("Table 4")
    first = add_menu(order.id, options["LEN"], options["STK"]).lines[0]
    second = add_menu(order.id, options["SAL"], options["STK"]).lines[-1]
    fire(order.id)

    relay()

    (ticket,) = board().cooking
    assert [(item.name, item.menu_line_id) for item in ticket.items] == [
        ("Lentils", first.id),
        ("Steak", first.id),
        ("Salad", second.id),
        ("Steak", second.id),
    ]


def test_the_board_shows_the_dishes_of_a_menu_with_the_ids_they_are_saved_with(menu):
    """Before the kitchen saves the round (no write yet), the board already shows each dish with the id it
    will keep: a tap on it marks that very dish."""
    options, _, _ = menu
    order = open_check("Table 4")
    add_menu(order.id, options["LEN"], options["STK"])
    fire(order.id)

    (shown,) = board().cooking
    assert shown.saved is False
    lentils, steak = shown.items
    run("kitchen.item.bump", {"ticket_id": str(shown.id), "item_ids": [str(steak.id)]})

    saved = Ticket.objects.get()
    assert [(item.id, item.name, item.status) for item in saved.items.all()] == [
        (lentils.id, "Lentils", "pending"),
        (steak.id, "Steak", "ready"),
    ]


def test_voiding_the_menu_in_the_till_strikes_all_its_dishes(relay, menu):
    options, _, _ = menu
    order = open_check("Table 4")
    (menu_line,) = add_menu(order.id, options["LEN"], options["STK"]).lines
    fire(order.id)
    relay()

    run(
        "sale.order.void_line",
        {"order_id": str(order.id), "line_id": str(menu_line.id), "reason": "Wrong table"},
    )
    relay()

    saved = Ticket.objects.get()
    assert [(item.name, item.status, item.void_reason) for item in saved.items.all()] == [
        ("Lentils", "voided", "Wrong table"),
        ("Steak", "voided", "Wrong table"),
    ]


def test_a_menu_of_services_only_is_not_cooked(menu):
    options, _, _ = menu
    setup("combo.combo.create", {"name": "Service pack", "price": 100, "tax_category_key": FOOD})
    setup("combo.group.create", {"combo": "Service pack", "name": "Service"})
    tip = setup("combo.option.create", {"combo": "Service pack", "group": "Service", "product": "TIP"})
    order = open_check("Table 4")
    add_menu(order.id, str(tip.id), combo="Service pack")

    with pytest.raises(Conflict) as refused:
        run("kitchen.ticket.send", {"order_id": str(order.id)}, ctx_for(actor="luis"))
    assert refused.value.code == "kitchen.nothing_to_cook"
    assert Ticket.objects.count() == 0

